"""Mutation-testing quality gate.

The gate runs after a candidate test passes the test runner. It rejects
tests whose Mutation Score Indicator is below the configured threshold,
forcing the generator to produce tests that actually detect regressions
rather than just exercising lines for coverage credit.
"""

from .gate import GateResult, run_gate
from .score import MutationScore, parse, parse_infection, parse_pest

__all__ = [
    "GateResult",
    "MutationScore",
    "parse",
    "parse_infection",
    "parse_pest",
    "run_gate",
]
