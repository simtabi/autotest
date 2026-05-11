"""Prompt builder.

Turns a ``GenerationRequest`` into the system + user messages we send to
the LLM. The prompt is plain text + XML tags (Anthropic's recommended
shape); separating prompt construction from the LLM call lets us snapshot-
test it cheaply without burning tokens.
"""

from __future__ import annotations

from .base import GenerationRequest


def build_messages(request: GenerationRequest) -> tuple[str, str]:
    """Return ``(system_prompt, user_prompt)`` ready to hand to the LLM.

    The split mirrors LiteLLM / OpenAI / Anthropic message conventions: the
    system message frames the role + the immutable rules; the user message
    carries the per-unit data and any retry feedback.
    """
    return _system_prompt(request), _user_prompt(request)


def _system_prompt(request: GenerationRequest) -> str:
    framework = request.conventions.test_framework.lower()
    return (
        "You are a senior test engineer. Your job is to write ONE test for the "
        f"function or method shown in the <unit> block, targeting the {framework} "
        "test framework. Output requirements:\n"
        "1. The test MUST be a single self-contained file that the project's "
        "test runner can execute as-is.\n"
        "2. The test MUST exercise the function's actual behaviour, not just "
        "instantiate the class. Aim to make the test fail if the function's "
        "body is mutated (off-by-one, condition flip, wrong return value).\n"
        "3. Match the project's existing test style and conventions shown in "
        "<sibling_tests>; copy import patterns, helper usage, and assertion "
        "style from there.\n"
        "4. Use the <conventions> block as ground truth about base test case, "
        "RefreshDatabase, namespaces, etc.\n"
        "5. If <previous_attempts> are present, every new attempt MUST address "
        "the error reported there -- do not regenerate the same failing shape.\n"
        "6. Output only the test file content in `test_code`, a short test "
        "name in `test_name` (matching the it('...') string for Pest, or the "
        "test_method_name for PHPUnit), and a one-line rationale.\n"
    )


def _user_prompt(request: GenerationRequest) -> str:
    """Body of the request. XML tags are Anthropic-recommended structure."""
    parts: list[str] = []

    parts.append("<unit>")
    parts.append(f"<file>{request.unit.file}</file>")
    parts.append(f"<name>{request.unit.name}</name>")
    parts.append(f"<kind>{request.unit.kind}</kind>")
    if request.unit.parent:
        parts.append(f"<parent>{request.unit.parent}</parent>")
    if request.unit.docblock:
        parts.append(f"<docblock>{request.unit.docblock}</docblock>")
    parts.append("<source>")
    parts.append(request.unit.source)
    parts.append("</source>")
    parts.append("</unit>")

    parts.append("<conventions>")
    parts.append(f"<framework>{request.conventions.test_framework}</framework>")
    if request.conventions.base_test_case:
        parts.append(f"<base_test_case>{request.conventions.base_test_case}</base_test_case>")
    if request.conventions.uses_refresh_database:
        parts.append("<refresh_database>true</refresh_database>")
    if request.conventions.namespace_root:
        parts.append(f"<namespace_root>{request.conventions.namespace_root}</namespace_root>")
    for key, value in request.conventions.extra.items():
        parts.append(f"<extra name=\"{key}\">{value}</extra>")
    parts.append("</conventions>")

    if request.sibling_tests:
        parts.append("<sibling_tests>")
        # Cap each example to keep token usage bounded; the LLM only needs to
        # learn the style, not memorise every test in the repo.
        for i, example in enumerate(request.sibling_tests[:3], start=1):
            parts.append(f"<example index=\"{i}\">")
            parts.append(example[:6_000])
            parts.append("</example>")
        parts.append("</sibling_tests>")

    if request.previous_attempts:
        parts.append("<previous_attempts>")
        for i, attempt in enumerate(request.previous_attempts, start=1):
            parts.append(f"<attempt index=\"{i}\">")
            parts.append("<test_code>")
            parts.append(attempt.test_code)
            parts.append("</test_code>")
            parts.append("<error>")
            parts.append(attempt.error)
            parts.append("</error>")
            parts.append("</attempt>")
        parts.append("</previous_attempts>")

    return "\n".join(parts)
