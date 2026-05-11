"""Writer / Reviewer composite generator.

Implements Anthropic's recommended two-pass quality pattern (per the
official Claude Code best-practices docs): one model writes the test,
another (typically a stronger model) critiques it, and the first model
revises based on that critique. Empirically catches assertion
weaknesses, missing edge cases, and "looks-right-but-doesn't-actually-
test-anything" stubs that a single-pass generator misses.

This is opt-in (--reviewer on the CLI) because it triples per-test LLM
spend. Default off keeps Phase 1's cost profile.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from pydantic import BaseModel, Field

from .base import GeneratedTest, GenerationRequest, Generator


class ReviewCritique(BaseModel):
    """Structured output from the reviewer pass.

    Kept structured (not free-form text) so the writer's revision prompt
    can address each finding individually instead of "consider all this
    advice", which empirically leads to ignored feedback.
    """

    findings: list[str] = Field(
        default_factory=list,
        description="Concrete problems with the draft: weak assertions, "
        "missing edge cases, untested branches, hallucinated APIs, etc.",
    )
    suggestions: list[str] = Field(
        default_factory=list,
        description="Concrete fixes for the findings, in the same order.",
    )
    ship_as_is: bool = Field(
        default=False,
        description="True if the draft is already strong enough to ship.",
    )

    @property
    def has_issues(self) -> bool:
        return not self.ship_as_is and bool(self.findings)


@dataclass(slots=True)
class WriterReviewerGenerator:
    """A Generator that runs writer -> reviewer -> writer-revises.

    Composes any two Generator instances. In production we use Sonnet
    for the writer + Opus for the reviewer (the stronger model spots
    issues the writer missed); for tests we use FakeGenerator chains.
    """

    writer: Generator
    reviewer: Reviewer

    def generate(self, request: GenerationRequest) -> GeneratedTest:
        draft = self.writer.generate(request)

        critique = self.reviewer.review(request, draft)
        if not critique.has_issues:
            return draft

        # Build a revision request: the same unit, but with the original
        # draft attached as a "previous attempt" carrying the reviewer's
        # findings as the "error" field. This piggy-backs on the retry-
        # feedback machinery the writer already understands.
        from .base import FailedAttempt

        revision_request = request.model_copy(
            update={
                "previous_attempts": [
                    *request.previous_attempts,
                    FailedAttempt(
                        test_code=draft.test_code,
                        error=_format_critique(critique),
                        output="",
                    ),
                ]
            }
        )

        return self.writer.generate(revision_request)


class Reviewer:
    """Pure interface for the review step. ``ClaudeReviewer`` is the
    real one; tests use ``FakeReviewer`` from generation/fake.py."""

    def review(self, request: GenerationRequest, draft: GeneratedTest) -> ReviewCritique:
        raise NotImplementedError


class ClaudeReviewer(Reviewer):
    """LiteLLM-backed reviewer. Uses a stronger model than the writer by
    default; the asymmetry is the whole point -- a same-strength
    reviewer tends to agree with whatever the writer produced."""

    def __init__(
        self,
        model: str = "claude-opus-4-7",
        api_key: str | None = None,
        max_tokens: int = 2_048,
        temperature: float = 0.1,
    ) -> None:
        self.model = model
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self.max_tokens = max_tokens
        self.temperature = temperature
        self._client = None

    def _ensure_client(self):
        if self._client is not None:
            return self._client

        if not self.api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set. Either export it or pass "
                "api_key=... when constructing ClaudeReviewer."
            )

        import instructor  # type: ignore[import-not-found]
        from litellm import completion  # type: ignore[import-not-found]

        self._client = instructor.from_litellm(completion)
        return self._client

    def review(self, request: GenerationRequest, draft: GeneratedTest) -> ReviewCritique:
        client = self._ensure_client()
        system = _reviewer_system_prompt()
        user = _reviewer_user_prompt(request, draft)

        return client.chat.completions.create(
            model=self.model,
            api_key=self.api_key,
            response_model=ReviewCritique,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )


def _reviewer_system_prompt() -> str:
    return (
        "You are a senior test engineer reviewing another engineer's draft test. "
        "Your job is to find concrete problems that would let a regression slip "
        "through the test. Look for:\n"
        "- assertions that don't actually verify the function's return value "
        "(e.g. asserting type but not value, asserting truthy but not the "
        "specific expected truthy value);\n"
        "- missing edge cases (empty input, zero, negative numbers, boundary "
        "conditions, null);\n"
        "- branches in the function under test that the test doesn't exercise;\n"
        "- references to APIs that don't exist in the project (hallucinated "
        "factory methods, made-up helpers, wrong class names);\n"
        "- assertions that would pass even if the function returned the wrong "
        "value (the classic 'test passes a mutated implementation' failure).\n"
        "\n"
        "Be specific: each finding should name what's wrong AND each suggestion "
        "should say what to add. If the draft is genuinely strong enough to "
        "ship, set ship_as_is=true and leave findings/suggestions empty."
    )


def _reviewer_user_prompt(request: GenerationRequest, draft: GeneratedTest) -> str:
    parts: list[str] = []
    parts.append("<function_under_test>")
    parts.append(f"<name>{request.unit.name}</name>")
    if request.unit.docblock:
        parts.append(f"<docblock>{request.unit.docblock}</docblock>")
    parts.append("<source>")
    parts.append(request.unit.source)
    parts.append("</source>")
    parts.append("</function_under_test>")

    parts.append("<draft_test>")
    parts.append(draft.test_code)
    parts.append("</draft_test>")

    parts.append(
        "Critique the draft. Output structured findings + suggestions per the "
        "ReviewCritique schema. If the draft is already strong, set "
        "ship_as_is=true."
    )
    return "\n".join(parts)


def _format_critique(critique: ReviewCritique) -> str:
    """Render a ``ReviewCritique`` as the structured-feedback string the
    writer's retry path expects (mirrors the mutation-gate feedback shape)."""
    lines = ["A reviewer flagged issues with this draft. Address each:"]
    for i, finding in enumerate(critique.findings, start=1):
        suggestion = critique.suggestions[i - 1] if i <= len(critique.suggestions) else ""
        lines.append(f"  {i}. FINDING: {finding}")
        if suggestion:
            lines.append(f"     FIX: {suggestion}")
    return "\n".join(lines)
