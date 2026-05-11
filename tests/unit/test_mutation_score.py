"""Mutation-score parser tests.

We pin against representative output snippets from both Pest 3 and
Infection so a tool-version bump that tweaks output formatting fails
loudly here instead of silently bypassing the quality gate.
"""

from __future__ import annotations

import pytest

from autotest.quality.score import parse, parse_infection, parse_pest


def test_parse_pest_recognises_msi_line():
    output = """
       PASS  Tests\\Unit\\FooTest
      ✓ it adds                                              0.01s

      Tests:    1 passed (1 assertions)
      Mutation Score Indicator (MSI): 87.5%
      Killed: 7
      Survived: 1
      Total mutants: 8
    """
    score = parse_pest(output)
    assert score is not None
    assert score.msi == 87.5
    assert score.mutants_killed == 7
    assert score.mutants_survived == 1
    assert score.mutants_total == 8


def test_parse_pest_handles_short_summary():
    output = "Score: 100%"
    score = parse_pest(output)
    assert score is not None
    assert score.msi == 100.0


def test_parse_pest_returns_none_when_no_score():
    score = parse_pest("Tests: 1 passed\nNo mutation summary here.")
    assert score is None


def test_parse_infection_summary_block():
    output = """
        Total Mutants: 12
        Killed Mutants: 9
        Escaped Mutants: 3
        Mutation Score Indicator (MSI): 75%
        Mutation Code Coverage: 92%
    """
    score = parse_infection(output)
    assert score is not None
    assert score.msi == 75.0
    assert score.mutants_killed == 9
    assert score.mutants_survived == 3
    assert score.mutants_total == 12


def test_parse_dispatches_by_format_name():
    assert parse("pest", "Score: 50%").msi == 50.0
    assert parse("infection", "Mutation Score Indicator (MSI): 33%").msi == 33.0


def test_parse_rejects_unknown_format():
    with pytest.raises(ValueError, match="Unsupported"):
        parse("nope", "anything")
