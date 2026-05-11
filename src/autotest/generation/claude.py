"""LiteLLM-backed generator.

Talks to whatever provider is configured (Anthropic by default; Azure /
OpenAI / Gemini / Ollama all work because LiteLLM normalises the API).
Uses Instructor for structured output so the response is already a
validated ``GeneratedTest`` -- no JSON-parsing of free-form LLM text in
our orchestrator.
"""

from __future__ import annotations

import os

from .base import GeneratedTest, GenerationRequest
from .prompt import build_messages


class ClaudeGenerator:
    """Generator backed by Claude via LiteLLM + Instructor.

    Cost defaults: Sonnet 4.6 for writes, Opus 4.7 for the Writer/Reviewer
    pass (Phase 3). For Phase 1 we use Sonnet only.
    """

    def __init__(
        self,
        model: str = "claude-sonnet-4-6",
        api_key: str | None = None,
        max_tokens: int = 4_096,
        temperature: float = 0.2,
    ) -> None:
        self.model = model
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self.max_tokens = max_tokens
        self.temperature = temperature
        # Import lazily so the rest of the package (inventory, CLI) works
        # without LiteLLM/Instructor + API credentials installed.
        self._client = None

    def _ensure_client(self):
        if self._client is not None:
            return self._client

        if not self.api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set. Either export it or pass "
                "api_key=... when constructing ClaudeGenerator."
            )

        try:
            import instructor  # type: ignore[import-not-found]
            from litellm import completion  # type: ignore[import-not-found]
        except ImportError as cause:
            raise RuntimeError(
                "litellm + instructor are required for the Claude generator. "
                "They are core deps, so this only happens in custom installs "
                "that pruned them; reinstall with `pip install simtabi-autotest`."
            ) from cause

        # Instructor wraps LiteLLM's `completion` so the response is parsed
        # into a Pydantic model with retries on validation failure.
        self._client = instructor.from_litellm(completion)
        return self._client

    def generate(self, request: GenerationRequest) -> GeneratedTest:
        client = self._ensure_client()
        system_prompt, user_prompt = build_messages(request)

        return client.chat.completions.create(
            model=self.model,
            api_key=self.api_key,
            response_model=GeneratedTest,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
