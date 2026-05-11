"""Language-adapter contract.

Each supported language ships an adapter that plugs in:

- the tree-sitter rules for walking source files,
- the shell commands to run the test suite + collect coverage,
- the shell commands to run the mutation tester + read the MSI score,
- the directory conventions for writing new test files.

The rest of the pipeline depends only on this contract, so adding a new
language is bounded to one file (plus tests).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from ..inventory.ast import AstRules


@dataclass(frozen=True, slots=True)
class TestRunCommand:
    """How to run the project's test suite.

    The runner shells out with ``cmd`` and parses ``coverage_path`` for the
    coverage report. ``cmd`` may contain ``{filter}`` which the runner will
    substitute with a test name when re-running a single generated test.
    """

    cmd: list[str]
    cwd: Path
    coverage_path: Path
    coverage_format: str  # "clover" | "lcov" | "cobertura"


@dataclass(frozen=True, slots=True)
class MutationRunCommand:
    """How to run the project's mutation tester."""

    cmd: list[str]
    cwd: Path
    score_format: str  # "pest" | "infection" | "stryker" | "mutmut"


class LanguageAdapter(Protocol):
    """Everything a language adapter must provide."""

    name: str
    extensions: tuple[str, ...]    # source-file extensions, e.g. (".php",)
    test_dir: Path                 # where to write new tests
    generated_test_subdir: str     # subdir under test_dir for AI-generated tests

    def ast_rules(self) -> AstRules: ...

    def test_command(self, project_root: Path) -> TestRunCommand: ...

    def mutation_command(self, project_root: Path) -> MutationRunCommand: ...

    def test_file_for(self, unit_file: Path, project_root: Path) -> Path:
        """Where the generated test for ``unit_file`` should live."""
        ...
