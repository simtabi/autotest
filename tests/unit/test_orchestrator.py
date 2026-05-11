"""End-to-end orchestrator tests with the in-process FakeGenerator.

Exercises the full pipeline (inventory -> generate -> write -> run ->
retry) without an LLM call or a real test runner. The test runner is
mocked at the subprocess layer.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from autotest.adapters.php import PhpAdapter
from autotest.generation.base import GeneratedTest
from autotest.generation.fake import FakeGenerator
from autotest.inventory.ast import DiscoveredUnit
from autotest.orchestrator import GenerateOptions, collect_units, generate_for_units
from autotest.verification.runner import RunResult

FIXTURE = Path(__file__).parent.parent / "fixtures" / "php" / "SampleService.php"


def _stub_unit(tmp_path: Path) -> DiscoveredUnit:
    """Standalone DiscoveredUnit so we don't depend on the AST walker."""
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


def test_collect_units_finds_public_methods_in_fixture():
    adapter = PhpAdapter()
    units = collect_units(FIXTURE, adapter)
    names = {u.name for u in units}
    assert "SampleService::add" in names
    assert "SampleService::increment" in names
    assert "bare_function" in names
    assert "SampleService::shouldNotAppear" not in names


def test_dry_run_does_not_touch_disk(tmp_path):
    adapter = PhpAdapter()
    unit = _stub_unit(tmp_path)
    gen = FakeGenerator()

    options = GenerateOptions(project_root=tmp_path, dry_run=True, max_attempts=1)
    summary = generate_for_units([unit], adapter, gen, options)

    assert len(summary.accepted) == 1
    # Dry-run path means we never wrote anything.
    test_path = adapter.test_file_for(unit.file, tmp_path)
    assert not test_path.exists()
    # The fake generator was still called exactly once.
    assert len(gen.calls) == 1


def test_orchestrator_accepts_a_passing_test(tmp_path):
    adapter = PhpAdapter()
    unit = _stub_unit(tmp_path)
    gen = FakeGenerator()

    options = GenerateOptions(project_root=tmp_path, max_attempts=1, run_formatter=False)

    # Mock the runner so subprocess never actually fires; pretend Pest
    # passed on the first attempt.
    with patch(
        "autotest.orchestrator.run_filtered",
        return_value=RunResult(passed=True, exit_code=0, stdout="OK", stderr=""),
    ):
        summary = generate_for_units([unit], adapter, gen, options)

    assert len(summary.accepted) == 1
    outcome = summary.accepted[0]
    assert outcome.test_path.exists()
    assert outcome.attempts == 1


def test_orchestrator_retries_on_failure_then_succeeds(tmp_path):
    adapter = PhpAdapter()
    unit = _stub_unit(tmp_path)

    call_count = {"n": 0}

    def responder(_request):
        call_count["n"] += 1
        # Hand back a slightly different test each attempt so the
        # orchestrator can tell them apart in the FailedAttempt log.
        return GeneratedTest(
            test_code=f"<?php it('try_{call_count['n']}', fn() => expect(1)->toBe(1));",
            test_name=f"try_{call_count['n']}",
            rationale="attempt",
        )

    gen = FakeGenerator(responder=responder)

    # First call fails, second call passes.
    side_effects = [
        RunResult(passed=False, exit_code=1, stdout="failure", stderr="expected 1 got 2"),
        RunResult(passed=True, exit_code=0, stdout="OK", stderr=""),
    ]

    options = GenerateOptions(project_root=tmp_path, max_attempts=3, run_formatter=False)

    with patch("autotest.orchestrator.run_filtered", side_effect=side_effects):
        summary = generate_for_units([unit], adapter, gen, options)

    assert len(summary.accepted) == 1
    assert summary.accepted[0].attempts == 2
    # And the second request carried the first attempt's failure as context.
    second_request = gen.calls[1]
    assert len(second_request.previous_attempts) == 1
    assert "expected 1 got 2" in second_request.previous_attempts[0].error


def test_orchestrator_rejects_after_max_attempts(tmp_path):
    adapter = PhpAdapter()
    unit = _stub_unit(tmp_path)
    gen = FakeGenerator()

    always_fail = RunResult(passed=False, exit_code=1, stdout="", stderr="nope")

    options = GenerateOptions(project_root=tmp_path, max_attempts=2, run_formatter=False)

    with patch("autotest.orchestrator.run_filtered", return_value=always_fail):
        summary = generate_for_units([unit], adapter, gen, options)

    assert len(summary.rejected) == 1
    outcome = summary.rejected[0]
    assert outcome.attempts == 2
    assert len(outcome.failed_attempts) == 2
    # Rejected candidates must NOT leave a test file lying around.
    assert outcome.test_path is None or not outcome.test_path.exists()
