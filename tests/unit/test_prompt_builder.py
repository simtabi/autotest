"""Snapshot-style tests for the prompt builder.

Prompts are cheap to construct but expensive to debug when wrong, so we
pin the shape with substring assertions on the structure (XML tags, key
sections) rather than full-text comparison -- the latter is brittle and
breaks every time we tweak wording.
"""

from __future__ import annotations

from pathlib import Path

from autotest.generation.base import (
    FailedAttempt,
    GenerationRequest,
    ProjectConventions,
)
from autotest.generation.prompt import build_messages
from autotest.inventory.ast import DiscoveredUnit


def _unit():
    return DiscoveredUnit(
        file=Path("/fake/Sample.php"),
        name="Sample::add",
        kind="method",
        visibility="public",
        start_line=10,
        end_line=12,
        source="public function add(int $a, int $b): int { return $a + $b; }",
        parent="Sample",
        signature="public function add(int $a, int $b): int",
        docblock="/** Add two ints. */",
    )


def test_system_prompt_names_the_test_framework():
    request = GenerationRequest(unit=_unit())
    system, _user = build_messages(request)
    assert "pest" in system.lower()


def test_user_prompt_carries_unit_metadata():
    request = GenerationRequest(unit=_unit())
    _system, user = build_messages(request)
    assert "<unit>" in user
    assert "Sample::add" in user
    assert "Sample" in user  # parent
    assert "public function add" in user
    assert "Add two ints" in user  # docblock


def test_user_prompt_includes_sibling_tests_when_provided():
    request = GenerationRequest(
        unit=_unit(),
        sibling_tests=["it('adds', fn() => expect(1+1)->toBe(2));"],
    )
    _system, user = build_messages(request)
    assert "<sibling_tests>" in user
    assert "expect(1+1)" in user


def test_user_prompt_caps_sibling_examples_at_three():
    """A repo with thousands of tests must not blow our token budget."""
    request = GenerationRequest(
        unit=_unit(),
        sibling_tests=[f"// example {i}" for i in range(20)],
    )
    _system, user = build_messages(request)
    # Only the first three examples should appear.
    assert "// example 0" in user
    assert "// example 1" in user
    assert "// example 2" in user
    assert "// example 3" not in user


def test_user_prompt_includes_previous_attempts_for_retry():
    request = GenerationRequest(
        unit=_unit(),
        previous_attempts=[
            FailedAttempt(
                test_code="<?php it('broken', fn() => expect(true)->toBeFalse());",
                error="Expected false, got true",
            )
        ],
    )
    _system, user = build_messages(request)
    assert "<previous_attempts>" in user
    assert "Expected false, got true" in user
    assert "broken" in user


def test_conventions_appear_in_user_prompt():
    request = GenerationRequest(
        unit=_unit(),
        conventions=ProjectConventions(
            test_framework="pest",
            uses_refresh_database=True,
            base_test_case="App\\Tests\\TestCase",
            namespace_root="App\\Tests\\Generated",
        ),
    )
    _system, user = build_messages(request)
    assert "App\\Tests\\TestCase" in user
    assert "refresh_database" in user
    assert "App\\Tests\\Generated" in user
