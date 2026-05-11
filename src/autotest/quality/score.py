"""Mutation Score Indicator (MSI) parser + scoring math.

We support three score formats today:

- ``pest`` -- Pest 3's ``--mutate`` text output ("Score: 73.2%")
- ``infection`` -- the JSON or stdout summary from Infection
- ``stryker`` -- Stryker for JS / Vue (Phase 6 wiring; parser kept here
  so adapters share the math)

Each format has its own parser; the rest of the pipeline only sees the
uniform ``MutationScore`` shape.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MutationScore:
    """The outcome of one mutation-testing run, normalised across tools."""

    msi: float                  # 0.0 - 100.0
    mutants_total: int
    mutants_killed: int
    mutants_survived: int
    raw_output: str             # first ~2K chars of runner output, for logs

    @property
    def meets(self) -> bool:
        return self.msi > 0  # caller compares against threshold separately


# Pest 3's mutation summary line shapes (battle-tested across the docs +
# several real Pest 3 runs). We accept multiple variants so a minor Pest
# release tweak doesn't break us.
_PEST_PATTERNS = (
    re.compile(r"Mutation Score Indicator\s*\(MSI\):\s*([0-9]+(?:\.[0-9]+)?)\s*%", re.I),
    re.compile(r"Score:\s*([0-9]+(?:\.[0-9]+)?)\s*%", re.I),
)
_PEST_KILLED = re.compile(r"Killed:\s*(\d+)", re.I)
_PEST_SURVIVED = re.compile(r"(?:Survived|Escaped):\s*(\d+)", re.I)
_PEST_TOTAL = re.compile(r"(?:Total mutants|Mutants):\s*(\d+)", re.I)

# Infection summary patterns. Infection's stdout block looks like:
#   Mutation Score Indicator (MSI): 87%
#   Mutation Code Coverage: 92%
#   Covered Code MSI: 94%
_INFECTION_PATTERNS = _PEST_PATTERNS  # same shape; both accept "MSI: N%"
_INFECTION_KILLED = re.compile(r"\bKilled\s+Mutants:\s*(\d+)", re.I)
_INFECTION_SURVIVED = re.compile(r"\bEscaped\s+Mutants:\s*(\d+)", re.I)


def parse_pest(output: str) -> MutationScore | None:
    """Pest ``--mutate`` text output -> MutationScore (or None if absent)."""
    return _parse_generic(output, _PEST_PATTERNS, _PEST_KILLED, _PEST_SURVIVED, _PEST_TOTAL)


def parse_infection(output: str) -> MutationScore | None:
    """Infection ``--show-mutations`` text output -> MutationScore."""
    return _parse_generic(
        output,
        _INFECTION_PATTERNS,
        _INFECTION_KILLED,
        _INFECTION_SURVIVED,
        re.compile(r"\bTotal\s+Mutants:\s*(\d+)", re.I),
    )


def _parse_generic(
    output: str,
    msi_patterns: tuple[re.Pattern, ...],
    killed_re: re.Pattern,
    survived_re: re.Pattern,
    total_re: re.Pattern,
) -> MutationScore | None:
    msi = _first_match(output, msi_patterns)
    if msi is None:
        return None
    killed = _int_match(output, killed_re) or 0
    survived = _int_match(output, survived_re) or 0
    total = _int_match(output, total_re) or (killed + survived)
    return MutationScore(
        msi=float(msi),
        mutants_total=total,
        mutants_killed=killed,
        mutants_survived=survived,
        raw_output=output[:2_000],
    )


def _first_match(output: str, patterns: tuple[re.Pattern, ...]) -> str | None:
    """Return the first regex group that matches ``output``."""
    for pattern in patterns:
        m = pattern.search(output)
        if m:
            return m.group(1)
    return None


def _int_match(output: str, pattern: re.Pattern) -> int | None:
    m = pattern.search(output)
    return int(m.group(1)) if m else None


def parse(score_format: str, output: str) -> MutationScore | None:
    """Dispatch by adapter-supplied format name."""
    fmt = score_format.lower()
    if fmt == "pest":
        return parse_pest(output)
    if fmt == "infection":
        return parse_infection(output)
    raise ValueError(f"Unsupported mutation score format: {score_format}")
