"""Test runner subprocess tests.

We don't actually run Pest here -- we run `/bin/true`, `/bin/false`, and a
deliberately-missing binary to verify the contract: pass / fail / not-
found-handled / timeout-handled.
"""

from __future__ import annotations

import sys
from pathlib import Path

from autotest.verification.runner import run_filtered

PYTHON = sys.executable  # always present, predictable exit codes


def test_run_filtered_returns_passed_for_zero_exit(tmp_path: Path):
    """python -c 'pass' exits 0 -> RunResult.passed is True."""
    result = run_filtered(
        cmd=[PYTHON, "-c", "pass"],
        cwd=tmp_path,
    )
    assert result.passed is True
    assert result.exit_code == 0
    assert result.timed_out is False


def test_run_filtered_reports_failure_for_nonzero_exit(tmp_path: Path):
    result = run_filtered(
        cmd=[PYTHON, "-c", "import sys; sys.exit(2)"],
        cwd=tmp_path,
    )
    assert result.passed is False
    assert result.exit_code == 2


def test_run_filtered_captures_stdout(tmp_path: Path):
    result = run_filtered(
        cmd=[PYTHON, "-c", "print('hello')"],
        cwd=tmp_path,
    )
    assert "hello" in result.stdout


def test_run_filtered_handles_missing_command(tmp_path: Path):
    result = run_filtered(
        cmd=["this-binary-definitely-does-not-exist-xyzzy"],
        cwd=tmp_path,
    )
    assert result.passed is False
    assert "not found" in result.stderr.lower()


def test_run_filtered_appends_filter_argument(tmp_path: Path):
    """When test_filter is given the runner appends `--filter=name`."""
    # Use python to introspect argv and exit non-zero if the flag is missing.
    script = (
        "import sys; sys.exit(0 if any('--filter=my_test' in a for a in sys.argv) else 1)"
    )
    result = run_filtered(
        cmd=[PYTHON, "-c", script],
        cwd=tmp_path,
        test_filter="my_test",
    )
    assert result.passed is True


def test_run_filtered_times_out(tmp_path: Path):
    """A long-running command must hit the timeout, not hang the suite."""
    result = run_filtered(
        cmd=[PYTHON, "-c", "import time; time.sleep(5)"],
        cwd=tmp_path,
        timeout=1,
    )
    assert result.timed_out is True
    assert result.passed is False
