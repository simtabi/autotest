"""Generator protocol + the request/response shapes every generator returns.

The Generator interface is intentionally tiny: one ``generate`` method that
turns a structured request into a structured response. That makes it trivial
to (a) swap in a different LLM provider, (b) mock the whole thing in tests,
and (c) plug in Qodo or any other CLI-based generator as a thin shim.
"""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, Field

from ..inventory.ast import DiscoveredUnit


class FailedAttempt(BaseModel):
    """A previous test that the runner rejected. Fed back into the next
    generation attempt so the LLM can fix what it got wrong."""

    test_code: str = Field(..., description="The PHP source of the failed test.")
    error: str = Field(..., description="Stderr / failure summary from the test runner.")
    output: str = Field(default="", description="Full stdout from the test runner.")


class ProjectConventions(BaseModel):
    """Project-level facts the generator should respect.

    Populated by the convention learner (Phase 4); kept as a flat dict so we
    can add new fields without breaking the protocol.
    """

    test_framework: str = Field(default="pest", description="pest | phpunit | vitest | etc.")
    uses_refresh_database: bool = Field(default=False)
    uses_factories: bool = Field(default=False)
    base_test_case: str | None = Field(default=None, description="FQCN of the project TestCase.")
    strict_types: bool = Field(default=True)
    namespace_root: str | None = Field(default=None, description="Root namespace for new test files.")
    extra: dict[str, str] = Field(default_factory=dict, description="Free-form conventions.")


class GenerationRequest(BaseModel):
    """All the input a generator needs to write one test."""

    model_config = {"arbitrary_types_allowed": True}

    unit: DiscoveredUnit
    sibling_tests: list[str] = Field(
        default_factory=list,
        description="Source of nearby existing test files, used as few-shot examples.",
    )
    conventions: ProjectConventions = Field(default_factory=ProjectConventions)
    previous_attempts: list[FailedAttempt] = Field(default_factory=list)


class GeneratedTest(BaseModel):
    """One candidate test, structured so the orchestrator can act on it.

    ``test_name`` matches the actual Pest ``it('...')`` or method name so the
    runner can target it with ``--filter``. ``rationale`` is for logs only --
    it never lands in the committed test file.
    """

    test_code: str = Field(..., description="Full PHP source of the test file.")
    test_name: str = Field(..., description="Test name, used by the runner's --filter.")
    rationale: str = Field(default="", description="Why this test, for logs only.")
    targets: list[str] = Field(
        default_factory=list,
        description="Fully-qualified names this test exercises (e.g. 'App\\Service::method').",
    )


class Generator(Protocol):
    """The one method every backend implements."""

    def generate(self, request: GenerationRequest) -> GeneratedTest: ...
