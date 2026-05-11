"""Top-level CLI smoke tests."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from autotest.cli import app

# Force a wide pseudo-terminal so Rich doesn't truncate the table-rendered
# output we're asserting against. Without this, Rich falls back to 80-column
# rendering with ellipsis and our substring assertions break.
runner = CliRunner(env={"COLUMNS": "200", "TERM": "xterm-256color"})

FIXTURE = Path(__file__).parent.parent / "fixtures" / "php" / "SampleService.php"


def test_help_lists_php_subcommand():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "php" in result.stdout.lower()


def test_version_prints_a_version_string():
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "simtabi-autotest" in result.stdout


def test_php_inventory_finds_public_units_in_fixture():
    result = runner.invoke(app, ["php", "inventory", str(FIXTURE)])
    assert result.exit_code == 0
    assert "SampleService::add" in result.stdout
    assert "SampleService::increment" in result.stdout
    assert "bare_function" in result.stdout
    # Non-public must not appear.
    assert "shouldNotAppear" not in result.stdout
    assert "alsoHidden" not in result.stdout


def test_php_inventory_exits_nonzero_for_empty_target(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    result = runner.invoke(app, ["php", "inventory", str(empty)])
    assert result.exit_code != 0
