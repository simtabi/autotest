"""Writer/Reviewer composite generator tests.

Verifies the two-pass flow:

- Reviewer says ``ship_as_is`` -> writer is called once, draft returned
  unchanged.
- Reviewer flags issues -> writer is called a second time with the
  reviewer's structured critique as a previous_attempt, so the revision
  prompt actually carries the feedback.
"""

from __future__ import annotations

from autotest.generation.base import GeneratedTest, GenerationRequest
from autotest.generation.fake import FakeGenerator, FakeReviewer
from autotest.generation.reviewer import (
    ReviewCritique,
    WriterReviewerGenerator,
    _format_critique,
)
from autotest.inventory.ast import DiscoveredUnit


def _request() -> GenerationRequest:
    unit = DiscoveredUnit(
        file=__import__("pathlib").Path("/fake/Sample.php"),
        name="Sample::add",
        kind="method",
        visibility="public",
        start_line=10,
        end_line=12,
        source="public function add(int $a, int $b): int { return $a + $b; }",
        parent="Sample",
        signature="public function add(int $a, int $b): int",
        docblock=None,
    )
    return GenerationRequest(unit=unit)


def test_ship_as_is_skips_revision():
    writer = FakeGenerator()
    reviewer = FakeReviewer(responder=lambda _r, _d: ReviewCritique(ship_as_is=True))
    gen = WriterReviewerGenerator(writer=writer, reviewer=reviewer)

    out = gen.generate(_request())

    # Writer called exactly once when reviewer is happy.
    assert len(writer.calls) == 1
    assert len(reviewer.calls) == 1
    assert isinstance(out, GeneratedTest)


def test_findings_trigger_revision_call():
    writer = FakeGenerator()
    reviewer = FakeReviewer(
        responder=lambda _r, _d: ReviewCritique(
            findings=["weak assertion"],
            suggestions=["use toBe(specific value)"],
            ship_as_is=False,
        )
    )
    gen = WriterReviewerGenerator(writer=writer, reviewer=reviewer)

    gen.generate(_request())

    # Writer called twice: once for draft, once for revision.
    assert len(writer.calls) == 2
    revision_request = writer.calls[1]
    # The revision MUST carry the reviewer's findings as a previous attempt
    # so the writer's prompt picks it up via the existing retry path.
    assert len(revision_request.previous_attempts) == 1
    feedback = revision_request.previous_attempts[0].error
    assert "weak assertion" in feedback
    assert "toBe(specific value)" in feedback


def test_revision_preserves_existing_previous_attempts():
    """If the request already had failed_attempts (e.g. from the
    orchestrator's mutation-gate retry), the reviewer's critique
    should be appended, not replace them."""
    from autotest.generation.base import FailedAttempt

    base_request = _request().model_copy(
        update={
            "previous_attempts": [
                FailedAttempt(test_code="old", error="prior failure", output=""),
            ]
        }
    )

    writer = FakeGenerator()
    reviewer = FakeReviewer(
        responder=lambda _r, _d: ReviewCritique(
            findings=["new issue"], suggestions=["fix it"], ship_as_is=False
        )
    )
    gen = WriterReviewerGenerator(writer=writer, reviewer=reviewer)

    gen.generate(base_request)

    revision_request = writer.calls[1]
    assert len(revision_request.previous_attempts) == 2
    assert revision_request.previous_attempts[0].error == "prior failure"
    assert "new issue" in revision_request.previous_attempts[1].error


def test_format_critique_includes_findings_and_suggestions():
    formatted = _format_critique(
        ReviewCritique(
            findings=["finding-a", "finding-b"],
            suggestions=["fix-a", "fix-b"],
        )
    )
    assert "finding-a" in formatted
    assert "finding-b" in formatted
    assert "fix-a" in formatted
    assert "fix-b" in formatted


def test_format_critique_handles_missing_suggestion():
    """If the LLM produced more findings than suggestions, the formatter
    must still render every finding instead of indexing past the list."""
    formatted = _format_critique(
        ReviewCritique(
            findings=["finding-a", "finding-b"],
            suggestions=["fix-a"],  # only one suggestion for two findings
        )
    )
    assert "finding-a" in formatted
    assert "finding-b" in formatted
    assert "fix-a" in formatted
