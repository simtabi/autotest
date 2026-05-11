"""Shell out to the project's test runner and capture pass/fail + output.

The runner is intentionally dumb: it knows how to start a subprocess, kill
it on timeout, and report status. The orchestrator decides what to do with
that information (retry, accept, reject).
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class RunResult:
    """The outcome of one test-runner invocation."""

    passed: bool
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool = False


def run_filtered(
    cmd: list[str],
    cwd: Path,
    test_filter: str | None = None,
    filter_flag: str = "--filter",
    timeout: int = 120,
) -> RunResult:
    """Run ``cmd`` in ``cwd``, optionally filtered to a single test.

    ``cmd`` is the base test-runner invocation (e.g.
    ``["vendor/bin/pest"]``). When ``test_filter`` is supplied we append
    ``--filter=<test_filter>`` (or whatever ``filter_flag`` says) so a
    single newly-generated test runs in isolation -- avoids accidentally
    failing the whole suite when only the new test is broken.
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
    except subprocess.TimeoutExpired as e:
        return RunResult(
            passed=False,
            exit_code=-1,
            stdout=e.stdout or "" if isinstance(e.stdout, str) else "",
            stderr=f"Test runner timed out after {timeout}s",
            timed_out=True,
        )
    except FileNotFoundError as e:
        return RunResult(
            passed=False,
            exit_code=127,
            stdout="",
            stderr=f"Test runner not found: {e}. Is it installed in {cwd}?",
        )

    return RunResult(
        passed=proc.returncode == 0,
        exit_code=proc.returncode,
        stdout=proc.stdout,
        stderr=proc.stderr,
    )
