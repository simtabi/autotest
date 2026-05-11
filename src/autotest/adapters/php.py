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
    # Later: app.command("generate")(generate), app.command("ci")(ci_mode), ...


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
