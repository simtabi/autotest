"""The mutation-testing quality gate.

After the test runner says "this test passes," we run mutation testing on
the production code under test with the candidate test present. If the
test kills >= ``threshold`` percent of mutants, it earned its keep. If
not, the test is rejected and the next generation attempt is given
feedback like "your test passes but doesn't catch mutants; write
stricter assertions."

This is the differentiator -- the cheap LLM-only approach mass-produces
tests that exercise lines without actually verifying behaviour. The gate
forces every shipped test to demonstrably catch at least one regression.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from .score import MutationScore, parse


@dataclass(frozen=True, slots=True)
class GateResult:
    """Did the candidate pass the gate?"""

    passed: bool
    score: MutationScore | None
    threshold: float
    reason: str = ""

    @property
    def msi(self) -> float | None:
        return self.score.msi if self.score else None


def run_gate(
    cmd: list[str],
    cwd: Path,
    score_format: str,
    threshold: float,
    test_filter: str | None = None,
    filter_flag: str = "--filter",
    timeout: int = 600,
) -> GateResult:
    """Run the mutation tester and decide accept/reject.

    Mutation tests are SLOW -- we default the timeout to 10 minutes and
    rely on the caller to scope ``--filter`` to one test so each call is
    bounded to mutating code that one test actually covers.
    """
    full_cmd = list(cmd)
    if test_filter:
        full_cmd.append(f"{filter_flag}={test_filter}")

    try:
        proc = subprocess.run(
            full_cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return GateResult(
            passed=False,
            score=None,
            threshold=threshold,
            reason=f"mutation runner timed out after {timeout}s",
        )
    except FileNotFoundError as e:
        return GateResult(
            passed=False,
            score=None,
            threshold=threshold,
            reason=f"mutation runner not found: {e}",
        )

    combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
    score = parse(score_format, combined)

    if score is None:
        return GateResult(
            passed=False,
            score=None,
            threshold=threshold,
            reason="could not parse mutation score from output",
        )

    if score.msi >= threshold:
        return GateResult(
            passed=True,
            score=score,
            threshold=threshold,
            reason=f"MSI {score.msi:.1f}% >= {threshold:.1f}%",
        )

    return GateResult(
        passed=False,
        score=score,
        threshold=threshold,
        reason=(
            f"MSI {score.msi:.1f}% < {threshold:.1f}% "
            f"(killed {score.mutants_killed}/{score.mutants_total})"
        ),
    )
