"""PHP adapter: Pest / PHPUnit + Infection / Pest mutation testing.

Wires the language-agnostic orchestrator to a PHP project's actual tooling.
Defaults assume a standard Pest 3 layout (which is what Ichava and most
modern Laravel projects use); knobs are exposed for repos that diverge.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from ..inventory.ast import AstRules, discover
from .base import MutationRunCommand, TestRunCommand

console = Console()


@dataclass(frozen=True, slots=True)
class PhpAdapter:
    name: str = "php"
    extensions: tuple[str, ...] = (".php",)
    test_dir: Path = Path("tests")
    generated_test_subdir: str = "Generated"

    def ast_rules(self) -> AstRules:
        # Loaded lazily so users who don't run PHP commands don't pay the
        # PHP grammar's install cost. Install via the `[php]` extra:
        #   pip install 'simtabi-autotest[php]'
        try:
            import tree_sitter_php  # type: ignore[import-not-found]
        except ImportError as cause:
            console.print(
                "[bold red]Missing dependency:[/bold red] the PHP tree-sitter "
                "grammar is not installed.\n"
                "Install it with: [cyan]pip install 'simtabi-autotest[php]'[/cyan]"
            )
            raise typer.Exit(code=2) from cause
        from tree_sitter import Language

        # Tree-sitter's PHP grammar uses `method_declaration` for class
        # methods and `function_definition` for top-level / namespace funcs.
        return AstRules(
            language=Language(tree_sitter_php.language_php()),
            class_node_types=("class_declaration", "interface_declaration", "trait_declaration"),
            method_node_types=("method_declaration", "function_definition"),
            name_field="name",
            visibility_node_types=("visibility_modifier",),
            docblock_node_types=("comment",),
        )

    def test_command(self, project_root: Path) -> TestRunCommand:
        return TestRunCommand(
            cmd=["vendor/bin/pest", "--coverage", "--coverage-clover=coverage.xml"],
            cwd=project_root,
            coverage_path=project_root / "coverage.xml",
            coverage_format="clover",
        )

    def mutation_command(self, project_root: Path) -> MutationRunCommand:
        # Pest 3 has built-in mutation testing. Falls back to Infection only
        # if the project explicitly opts out via .autotest.yml (later phase).
        return MutationRunCommand(
            cmd=["vendor/bin/pest", "--mutate", "--min=60"],
            cwd=project_root,
            score_format="pest",
        )

    def test_file_for(self, unit_file: Path, project_root: Path) -> Path:
        # src/Services/IconBrowserService.php -> tests/Generated/Services/IconBrowserServiceTest.php
        try:
            rel = unit_file.relative_to(project_root / "src")
        except ValueError:
            rel = Path(unit_file.name)
        return (
            project_root
            / self.test_dir
            / self.generated_test_subdir
            / rel.with_name(f"{rel.stem}Test.php")
        )


_adapter = PhpAdapter()


def register(app: typer.Typer) -> None:
    """Mount this adapter's commands on the parent Typer app."""
    app.command("inventory")(inventory)
    app.command("generate")(generate)


def inventory(
    target: Path = typer.Argument(..., help="PHP source file or directory to scan."),
) -> None:
    """List every public method / function in ``target``.

    Phase-0 deliverable: proves the tree-sitter PHP integration end-to-end.
    Later phases layer coverage + churn filtering on top of this list.
    """
    files = _collect_php_files(target)
    if not files:
        console.print(f"[yellow]No PHP files found under {target}[/yellow]")
        raise typer.Exit(code=1)

    rules = _adapter.ast_rules()
    table = Table(title=f"Public units in {target}", show_lines=False)
    table.add_column("File", style="cyan", overflow="fold")
    table.add_column("Unit", style="green")
    table.add_column("Lines", justify="right")
    table.add_column("Signature", overflow="fold")

    total = 0
    for file in files:
        for unit in discover(file, rules):
            try:
                rel = file.relative_to(target if target.is_dir() else target.parent)
            except ValueError:
                rel = file
            table.add_row(
                str(rel),
                unit.name,
                f"{unit.start_line}-{unit.end_line}",
                unit.signature[:80],
            )
            total += 1

    console.print(table)
    console.print(f"\n[bold]{total}[/bold] testable unit(s) discovered.")


def _collect_php_files(target: Path) -> list[Path]:
    if target.is_file():
        return [target] if target.suffix == ".php" else []
    return sorted(p for p in target.rglob("*.php") if not _is_vendor(p))


def _is_vendor(path: Path) -> bool:
    """Skip third-party code and build artifacts we never want to test."""
    parts = set(path.parts)
    return bool(parts & {"vendor", "node_modules", ".phpunit.cache", "build"})


def generate(
    target: Path = typer.Argument(..., help="PHP source file or directory to generate tests for."),
    project_root: Path = typer.Option(
        Path.cwd(), "--project-root", help="Root of the PHP project (where vendor/, tests/ live)."
    ),
    method: str | None = typer.Option(
        None, "--method", help="Only generate a test for this method (matches by name)."
    ),
    max_attempts: int = typer.Option(3, "--max-attempts", help="Per-unit retry budget."),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Don't write or run; print what would be generated."
    ),
    generator_name: str = typer.Option(
        "claude", "--generator", help="Generator backend: claude | fake."
    ),
    model: str = typer.Option(
        "claude-sonnet-4-6", "--model", help="LLM model id (LiteLLM format)."
    ),
    mutation_gate: bool = typer.Option(
        True,
        "--mutation-gate/--no-mutation-gate",
        help="Reject tests that don't kill enough mutants of the code under test.",
    ),
    mutation_min: float = typer.Option(
        60.0, "--mutation-min", help="MSI threshold in percent (0-100)."
    ),
    mutation_timeout: int = typer.Option(
        600, "--mutation-timeout", help="Per-test mutation runner timeout in seconds."
    ),
) -> None:
    """Generate tests for every public method / function in ``target``.

    Pipeline: AST inventory -> LLM generate -> write -> run Pest with
    ``--filter`` -> on pass, run the mutation gate -> accept iff MSI
    meets ``--mutation-min``. Failures (runner or gate) feed structured
    error context back into the next attempt up to ``--max-attempts``.
    """
    # Imports kept local so the inventory command stays fast and doesn't
    # eagerly pull in LiteLLM at module import time.
    from ..orchestrator import GenerateOptions, collect_units, generate_for_units
    from ..output.reporter import render_summary

    units = collect_units(target, _adapter)
    if method:
        units = [u for u in units if u.name == method or u.name.endswith(f"::{method}")]

    if not units:
        console.print(f"[yellow]No matching public units in {target}[/yellow]")
        raise typer.Exit(code=1)

    gen = _resolve_generator(generator_name, model)

    options = GenerateOptions(
        project_root=project_root.resolve(),
        max_attempts=max_attempts,
        dry_run=dry_run,
        mutation_gate=mutation_gate,
        mutation_min=mutation_min,
        mutation_timeout=mutation_timeout,
    )

    summary = generate_for_units(units=units, adapter=_adapter, generator=gen, options=options)
    render_summary(summary, console)

    if summary.rejected and not dry_run:
        raise typer.Exit(code=1)


def _resolve_generator(name: str, model: str):
    """Look up a generator by short name. Kept tiny so adding 'qodo' or
    'openai' later is a one-line change."""
    name = name.lower()
    if name == "fake":
        from ..generation.fake import FakeGenerator

        return FakeGenerator()
    if name == "claude":
        from ..generation.claude import ClaudeGenerator

        return ClaudeGenerator(model=model)
    raise typer.BadParameter(f"Unknown generator: {name}. Use 'claude' or 'fake'.")
