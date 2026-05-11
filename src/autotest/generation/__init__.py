"""Test generator backends + the shared request/response contract."""

from .base import (
    FailedAttempt,
    GeneratedTest,
    GenerationRequest,
    Generator,
    ProjectConventions,
)
from .claude import ClaudeGenerator
from .fake import FakeGenerator, FakeReviewer
from .reviewer import (
    ClaudeReviewer,
    ReviewCritique,
    Reviewer,
    WriterReviewerGenerator,
)

__all__ = [
    "ClaudeGenerator",
    "ClaudeReviewer",
    "FailedAttempt",
    "FakeGenerator",
    "FakeReviewer",
    "GeneratedTest",
    "GenerationRequest",
    "Generator",
    "ProjectConventions",
    "ReviewCritique",
    "Reviewer",
    "WriterReviewerGenerator",
]
