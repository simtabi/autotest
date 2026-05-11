"""In-process fake generator used by tests.

Lets us exercise the full orchestrator pipeline (prompt -> generate ->
write -> run -> retry) without an API call. The fake stores every request
it sees, so tests can also assert on the prompt context the orchestrator
hands to a real generator.
"""

from __future__ import annotations

from collections.abc import Callable

from .base import GeneratedTest, GenerationRequest


class FakeGenerator:
    """A deterministic ``Generator`` for tests.

    Pass ``responder`` to compute the response from the request, or fall
    back to a canned response that names the test after the unit. Every
    call is recorded in ``calls`` for later inspection.
    """

    def __init__(
        self,
        responder: Callable[[GenerationRequest], GeneratedTest] | None = None,
    ) -> None:
        self._responder = responder or _default_response
        self.calls: list[GenerationRequest] = []

    def generate(self, request: GenerationRequest) -> GeneratedTest:
        self.calls.append(request)
        return self._responder(request)


def _default_response(request: GenerationRequest) -> GeneratedTest:
    """A minimal Pest test that just instantiates and exists. Useful for
    smoke-testing the wiring; would be rejected by the mutation gate."""
    safe_name = request.unit.name.replace("::", "_").replace("\\", "_")
    test_name = f"it_exercises_{safe_name}"
    body = f"""<?php

declare(strict_types=1);

// Stub test produced by the autotest FakeGenerator. Replace with a real
// generator to get tests that actually exercise the function.

it('{test_name}', function () {{
    expect(true)->toBeTrue();
}});
"""
    return GeneratedTest(
        test_code=body,
        test_name=test_name,
        rationale="Stub from FakeGenerator (test infrastructure only).",
        targets=[request.unit.name],
    )
