"""End-to-end test of the AST walker on a real PHP fixture.

This is the only test that actually parses a real source file. Higher-level
orchestration tests will mock out the walker; this one pins the contract
between us and tree-sitter so a grammar update can't silently break the
output shape.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from autotest.adapters.php import PhpAdapter
from autotest.inventory.ast import discover

FIXTURE = Path(__file__).parent.parent / "fixtures" / "php" / "SampleService.php"


@pytest.fixture()
def php_units():
    return discover(FIXTURE, PhpAdapter().ast_rules())


def test_finds_the_public_method(php_units):
    names = {u.name for u in php_units}
    assert "SampleService::add" in names


def test_finds_the_other_public_method(php_units):
    names = {u.name for u in php_units}
    assert "SampleService::increment" in names


def test_includes_top_level_function(php_units):
    names = {u.name for u in php_units}
    assert "bare_function" in names


def test_excludes_protected_methods(php_units):
    """`shouldNotAppear` is protected -- the walker must skip it."""
    names = {u.name for u in php_units}
    assert "SampleService::shouldNotAppear" not in names


def test_excludes_private_methods(php_units):
    names = {u.name for u in php_units}
    assert "SampleService::alsoHidden" not in names


def test_captures_signature_first_line(php_units):
    add = next(u for u in php_units if u.name == "SampleService::add")
    assert "function add" in add.signature
    assert "int $a, int $b" in add.signature


def test_captures_line_range(php_units):
    add = next(u for u in php_units if u.name == "SampleService::add")
    assert add.start_line < add.end_line
    assert add.start_line > 0


def test_captures_full_source(php_units):
    add = next(u for u in php_units if u.name == "SampleService::add")
    assert "return $a + $b" in add.source


def test_attaches_leading_docblock(php_units):
    add = next(u for u in php_units if u.name == "SampleService::add")
    # The fixture has a docblock on `add`; this pins that the walker
    # actually attaches it to the unit.
    assert add.docblock is not None
    assert "Add the two integers" in add.docblock
