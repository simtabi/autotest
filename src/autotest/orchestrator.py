"""End-to-end pipeline: discover -> generate -> verify -> (retry) -> write.

This is where the language adapter, generator, runner, and writer come
together. Stays language-agnostic by depending only on the adapter
protocol and the generator protocol; per-language commands inject the
concrete adapter and we keep everything else identical across PHP / JS /
Python.

Mutation testing happens in a separate quality.gate step that the CLI
will call after this orchestrator returns. We split that so users can
opt out (``--no-mutation-gate``) or run it manually on a batch.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .adapters.base import LanguageAdapter
from .generation.base import (
    FailedAttempt,
    GeneratedTest,
    GenerationRequest,
    Generator,
    ProjectConventions,
)
from .inventory.ast import DiscoveredUnit, discover
from .output.writer import WriteResult, remove_test, write_test
from .verification.runner import RunResult, run_filtered


@dataclass(slots=True)
class UnitOutcome:
    """What happened to one testable unit during a generation run."""

    unit: DiscoveredUnit
    accepted: bool
    attempts: int
    test_path: Path | None = None
    final_test: GeneratedTest | None = None
    last_run: RunResult | None = None
    write: WriteResult | None = None
    failed_attempts: list[FailedAttempt] = field(default_factory=list)
    reason: str = ""


@dataclass(slots=True)
class RunSummary:
    """The aggregate report from one orchestrator run."""

    outcomes: list[UnitOutcome] = field(default_factory=list)

    @property
    def accepted(self) -> list[UnitOutcome]:
        return [o for o in self.outcomes if o.accepted]

    @property
    def rejected(self) -> list[UnitOutcome]:
        return [o for o in self.outcomes if not o.accepted]


@dataclass(slots=True)
class GenerateOptions:
    """User-facing knobs for one ``generate`` invocation."""

    project_root: Path
    max_attempts: int = 3
    dry_run: bool = False
    run_formatter: bool = True
    test_runner_timeout: int = 120
    sibling_test_examples: int = 3


def generate_for_units(
    units: list[DiscoveredUnit],
    adapter: LanguageAdapter,
    generator: Generator,
    options: GenerateOptions,
    conventions: ProjectConventions | None = None,
    sibling_test_provider=None,
) -> RunSummary:
    """Run the full pipeline over every unit and return the aggregate.

    ``sibling_test_provider`` is a ``(unit) -> list[str]`` callable that
    returns sibling test sources to use as few-shot examples. The default
    (None) means "no examples"; Phase 4 plugs in a smarter learner.
    """
    summary = RunSummary()
    conventions = conventions or ProjectConventions()

    for unit in units:
        outcome = _generate_one(
            unit=unit,
            adapter=adapter,
            generator=generator,
            options=options,
            conventions=conventions,
            sibling_test_provider=sibling_test_provider,
        )
        summary.outcomes.append(outcome)

    return summary


def _generate_one(
    *,
    unit: DiscoveredUnit,
    adapter: LanguageAdapter,
    generator: Generator,
    options: GenerateOptions,
    conventions: ProjectConventions,
    sibling_test_provider,
) -> UnitOutcome:
    test_path = adapter.test_file_for(unit.file, options.project_root)
    sibling_tests = (
        sibling_test_provider(unit)[: options.sibling_test_examples]
        if sibling_test_provider is not None
        else []
    )

    failed: list[FailedAttempt] = []
    test_run_cmd = adapter.test_command(options.project_root)
    formatter_cmd = _formatter_cmd_for(adapter, options)

    for attempt in range(1, options.max_attempts + 1):
        request = GenerationRequest(
            unit=unit,
            sibling_tests=sibling_tests,
            conventions=conventions,
            previous_attempts=failed,
        )
        candidate = generator.generate(request)

        if options.dry_run:
            # In dry-run mode we don't touch disk or run anything; just
            # return what the LLM would have produced.
            return UnitOutcome(
                unit=unit,
                accepted=True,
                attempts=attempt,
                test_path=test_path,
                final_test=candidate,
                reason="dry-run",
            )

        write = write_test(
            path=test_path,
            content=candidate.test_code,
            formatter_cmd=formatter_cmd if options.run_formatter else None,
            formatter_cwd=options.project_root,
        )

        run = run_filtered(
            cmd=test_run_cmd.cmd,
            cwd=test_run_cmd.cwd,
            test_filter=candidate.test_name,
            timeout=options.test_runner_timeout,
        )

        if run.passed:
            return UnitOutcome(
                unit=unit,
                accepted=True,
                attempts=attempt,
                test_path=test_path,
                final_test=candidate,
                last_run=run,
                write=write,
                failed_attempts=failed,
                reason="passed",
            )

        # Failed -- remove the candidate and feed the error back so the
        # next attempt can fix it.
        remove_test(test_path)
        failed.append(
            FailedAttempt(
                test_code=candidate.test_code,
                error=(run.stderr or run.stdout)[:4_000],
                output=run.stdout[:4_000],
            )
        )

    return UnitOutcome(
        unit=unit,
        accepted=False,
        attempts=options.max_attempts,
        test_path=None,
        final_test=None,
        last_run=run if "run" in locals() else None,
        failed_attempts=failed,
        reason=f"all {options.max_attempts} attempts failed",
    )


def _formatter_cmd_for(adapter: LanguageAdapter, options: GenerateOptions) -> list[str] | None:
    """PHP adapters use Pint when available. Other adapters override via
    a future ``formatter_command`` hook on the adapter protocol; for now
    we feature-detect by adapter name."""
    if adapter.name == "php":
        pint = options.project_root / "vendor" / "bin" / "pint"
        if pint.exists():
            return [str(pint)]
    return None


def collect_units(
    target: Path,
    adapter: LanguageAdapter,
    rules=None,
) -> list[DiscoveredUnit]:
    """Convenience: walk ``target`` (file or dir) and return discoverable
    units the adapter cares about. Used by the CLI ``generate`` command
    so it doesn't have to know about tree-sitter."""
    ast_rules = rules or adapter.ast_rules()
    extensions = set(adapter.extensions)
    files: list[Path] = []
    if target.is_file() and target.suffix in extensions:
        files = [target]
    elif target.is_dir():
        for ext in extensions:
            files.extend(sorted(p for p in target.rglob(f"*{ext}") if not _is_skip_dir(p)))

    units: list[DiscoveredUnit] = []
    for f in files:
        units.extend(discover(f, ast_rules))
    return units


def _is_skip_dir(path: Path) -> bool:
    """Common directories we never want to scan."""
    parts = set(path.parts)
    return bool(parts & {"vendor", "node_modules", ".phpunit.cache", "build", "dist", "__pycache__"})
