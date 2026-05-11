"""Tests for the mutation-gate subprocess wrapper.

Like the test runner tests, these use Python subprocesses with canned
output so we exercise the parse + threshold logic without needing Pest
or Infection installed.
"""

from __future__ import annotations

import sys
from pathlib import Path

from autotest.quality.gate import run_gate

PYTHON = sys.executable


def test_gate_passes_when_msi_meets_threshold(tmp_path: Path):
    # A subprocess that prints a Pest-style MSI line then exits 0.
    cmd = [PYTHON, "-c", "print('Mutation Score Indicator (MSI): 80%')"]
    result = run_gate(cmd=cmd, cwd=tmp_path, score_format="pest", threshold=60.0)
    assert result.passed is True
    assert result.score is not None
    assert result.msi == 80.0


def test_gate_rejects_below_threshold(tmp_path: Path):
    cmd = [PYTHON, "-c", "print('Mutation Score Indicator (MSI): 30%')"]
    result = run_gate(cmd=cmd, cwd=tmp_path, score_format="pest", threshold=60.0)
    assert result.passed is False
    assert result.msi == 30.0
    assert "< 60.0%" in result.reason


def test_gate_rejects_when_score_unparseable(tmp_path: Path):
    cmd = [PYTHON, "-c", "print('no msi line here')"]
    result = run_gate(cmd=cmd, cwd=tmp_path, score_format="pest", threshold=60.0)
    assert result.passed is False
    assert result.score is None
    assert "parse" in result.reason.lower()


def test_gate_appends_filter_flag(tmp_path: Path):
    """When test_filter is given the runner appends `--filter=<name>`."""
    script = (
        "import sys; "
        "ok = any('--filter=my_t' in a for a in sys.argv); "
        "print('Mutation Score Indicator (MSI): 100%') if ok else print('no'); "
        "sys.exit(0)"
    )
    result = run_gate(
        cmd=[PYTHON, "-c", script],
        cwd=tmp_path,
        score_format="pest",
        threshold=50.0,
        test_filter="my_t",
    )
    assert result.passed is True


def test_gate_handles_missing_binary(tmp_path: Path):
    result = run_gate(
        cmd=["this-binary-definitely-does-not-exist-zzyzx"],
        cwd=tmp_path,
        score_format="pest",
        threshold=60.0,
    )
    assert result.passed is False
    assert "not found" in result.reason.lower()


def test_gate_times_out(tmp_path: Path):
    result = run_gate(
        cmd=[PYTHON, "-c", "import time; time.sleep(5)"],
        cwd=tmp_path,
        score_format="pest",
        threshold=60.0,
        timeout=1,
    )
    assert result.passed is False
    assert "timed out" in result.reason.lower()
