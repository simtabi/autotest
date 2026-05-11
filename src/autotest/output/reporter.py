"""Render a Rich-formatted summary of an orchestrator run."""

from __future__ import annotations

from rich.console import Console
from rich.table import Table

from ..orchestrator import RunSummary


def render_summary(summary: RunSummary, console: Console | None = None) -> None:
    """Print one table per generation outcome (accepted / rejected) plus
    a totals line. Keeps the CLI output skimmable even on a 100-unit run."""
    console = console or Console()

    table = Table(title="Generation results", show_lines=False)
    table.add_column("Unit", style="cyan", overflow="fold")
    table.add_column("Status", justify="center")
    table.add_column("Attempts", justify="right")
    table.add_column("Path", style="dim", overflow="fold")
    table.add_column("Reason", overflow="fold")

    for outcome in summary.outcomes:
        status = "[green]ACCEPTED[/green]" if outcome.accepted else "[red]REJECTED[/red]"
        table.add_row(
            outcome.unit.name,
            status,
            str(outcome.attempts),
            str(outcome.test_path) if outcome.test_path else "-",
            outcome.reason,
        )

    console.print(table)
    console.print(
        f"\n[bold]{len(summary.accepted)}[/bold] accepted, "
        f"[bold]{len(summary.rejected)}[/bold] rejected, "
        f"[bold]{len(summary.outcomes)}[/bold] total."
    )
