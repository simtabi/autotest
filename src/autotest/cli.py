"""Top-level Typer CLI.

Each supported language gets its own sub-Typer (`autotest php ...`,
`autotest js ...`, etc.). The sub-Typers delegate to a single shared
orchestrator with the appropriate language adapter injected.
"""

from __future__ import annotations

import typer
from rich.console import Console

from . import __version__
from .adapters import php as php_adapter

app = typer.Typer(
    name="autotest",
    help="AI-driven test generation with a mutation-testing quality gate.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)

console = Console()


@app.callback()
def main(
    ctx: typer.Context,
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output."),
) -> None:
    """[bold]simtabi-autotest[/bold] -- generate tests, verify they kill mutants, commit only the survivors."""
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose


@app.command()
def version() -> None:
    """Print the installed version and exit."""
    console.print(f"simtabi-autotest [bold cyan]{__version__}[/bold cyan]")


# Sub-Typer per language. Each adapter exposes a `register(app)` hook that
# attaches its commands; the CLI itself stays thin and just routes.
php_app = typer.Typer(
    name="php",
    help="Generate tests for PHP projects (Pest / PHPUnit + Infection / Pest mutation).",
    no_args_is_help=True,
)
php_adapter.register(php_app)
app.add_typer(php_app, name="php")


# JS / Vue / Python adapters will plug in the same way once their modules land.
# Stubs are left here intentionally as breadcrumbs for the next phases:
#
# from .adapters import javascript as js_adapter
# js_app = typer.Typer(name="js", help="...")
# js_adapter.register(js_app)
# app.add_typer(js_app, name="js")


if __name__ == "__main__":
    app()
