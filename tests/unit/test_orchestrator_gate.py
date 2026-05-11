"""Orchestrator behaviour with the mutation gate.

Covers four flows:

1. ``mutation_gate=False`` short-circuits the gate entirely.
2. Gate passes -> outcome accepted with gate metadata attached.
3. Gate fails -> retry triggered with structured feedback in the next
   request's previous_attempts (the LLM gets to see WHY the gate
   rejected its first attempt).
4. Repeated gate failures exhaust max_attempts and the unit is rejected.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from autotest.adapters.php import PhpAdapter
from autotest.generation.base import GeneratedTest
from autotest.generation.fake import FakeGenerator
from autotest.inventory.ast import DiscoveredUnit
from autotest.orchestrator import GenerateOptions, generate_for_units
from autotest.quality.gate import GateResult
from autotest.quality.score import MutationScore
from autotest.verification.runner import RunResult


def _stub_unit(tmp_path: Path) -> DiscoveredUnit:
    source_file = tmp_path / "src" / "Sample.php"
    source_file.parent.mkdir(parents=True, exist_ok=True)
    source_file.write_text("<?php class Sample { public function add(): int { return 1; } }\n")
    return DiscoveredUnit(
        file=source_file,
        name="Sample::add",
        kind="method",
        visibility="public",
        start_line=1,
        end_line=1,
        source="public function add(): int { return 1; }",
        parent="Sample",
        signature="public function add(): int",
        docblock=None,
    )


def _passing_run() -> RunResult:
    return RunResult(passed=True, exit_code=0, stdout="OK", stderr="")


def _high_msi_gate() -> GateResult:
    score = MutationScore(
        msi=87.5,
        mutants_total=8,
        mutants_killed=7,
        mutants_survived=1,
        raw_output="MSI 87.5%",
    )
    return GateResult(passed=True, score=score, threshold=60.0, reason="MSI 87.5% >= 60.0%")


def _low_msi_gate() -> GateResult:
    score = MutationScore(
        msi=30.0,
        mutants_total=10,
        mutants_killed=3,
        mutants_survived=7,
        raw_output="MSI 30%",
    )
    return GateResult(passed=False, score=score, threshold=60.0, reason="MSI 30% < 60%")


def test_no_mutation_gate_short_circuits(tmp_path):
    """With mutation_gate=False the orchestrator never calls run_gate."""
    adapter = PhpAdapter()
    unit = _stub_unit(tmp_path)
    gen = FakeGenerator()

    options = GenerateOptions(
        project_root=tmp_path,
        max_attempts=1,
        run_formatter=False,
        mutation_gate=False,
    )

    with (
        patch("autotest.orchestrator.run_filtered", return_value=_passing_run()),
        patch("autotest.orchestrator.run_gate") as run_gate_mock,
    ):
        summary = generate_for_units([unit], adapter, gen, options)

    assert len(summary.accepted) == 1
    assert summary.accepted[0].gate is None
    run_gate_mock.assert_not_called()


def test_gate_passes_attaches_metadata(tmp_path):
    adapter = PhpAdapter()
    unit = _stub_unit(tmp_path)
    gen = FakeGenerator()

    options = GenerateOptions(project_root=tmp_path, max_attempts=1, run_formatter=False)

    with (
        patch("autotest.orchestrator.run_filtered", return_value=_passing_run()),
        patch("autotest.orchestrator.run_gate", return_value=_high_msi_gate()),
    ):
        summary = generate_for_units([unit], adapter, gen, options)

    assert len(summary.accepted) == 1
    outcome = summary.accepted[0]
    assert outcome.gate is not None
    assert outcome.gate.passed is True
    assert outcome.gate.msi == 87.5
    assert "mutation gate" in outcome.reason


def test_gate_fail_retries_with_feedback(tmp_path):
    adapter = PhpAdapter()
    unit = _stub_unit(tmp_path)

    call_count = {"n": 0}

    def responder(_request):
        call_count["n"] += 1
        return GeneratedTest(
            test_code=f"<?php it('a{call_count['n']}', fn() => expect(true)->toBeTrue());",
            test_name=f"a{call_count['n']}",
            rationale="r",
        )

    gen = FakeGenerator(responder=responder)

    options = GenerateOptions(project_root=tmp_path, max_attempts=3, run_formatter=False)

    # Both runner calls pass; gate fails first, then passes.
    with (
        patch("autotest.orchestrator.run_filtered", return_value=_passing_run()),
        patch(
            "autotest.orchestrator.run_gate",
            side_effect=[_low_msi_gate(), _high_msi_gate()],
        ),
    ):
        summary = generate_for_units([unit], adapter, gen, options)

    assert len(summary.accepted) == 1
    accepted = summary.accepted[0]
    assert accepted.attempts == 2
    assert accepted.gate.msi == 87.5

    # The second LLM call must carry the gate's structured feedback so
    # the model can write stricter assertions on retry.
    second_request = gen.calls[1]
    assert len(second_request.previous_attempts) == 1
    feedback = second_request.previous_attempts[0].error
    assert "mutation gate" in feedback.lower()
    assert "strengthen" in feedback.lower()


def test_gate_fail_exhausts_attempts(tmp_path):
    adapter = PhpAdapter()
    unit = _stub_unit(tmp_path)
    gen = FakeGenerator()

    options = GenerateOptions(project_root=tmp_path, max_attempts=2, run_formatter=False)

    with (
        patch("autotest.orchestrator.run_filtered", return_value=_passing_run()),
        patch("autotest.orchestrator.run_gate", return_value=_low_msi_gate()),
    ):
        summary = generate_for_units([unit], adapter, gen, options)

    assert len(summary.rejected) == 1
    outcome = summary.rejected[0]
    assert outcome.attempts == 2
    assert len(outcome.failed_attempts) == 2
