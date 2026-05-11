# simtabi-autotest

> AI-driven test generation with a **mutation-testing quality gate**. Tests that don't kill mutants don't ship.

Mass-generated AI tests are easy to produce and just as easy to pad coverage with — but coverage going up while real bugs slip through is the well-documented failure mode in 2026. `simtabi-autotest` short-circuits that by treating every generated test as a hypothesis and using mutation testing as the verifier: if your generated test can't detect a mutated version of the function under test, the test is rejected before it ever lands in your tree.

## Status

**Alpha (Phase 2 / 7).** Inventory + generate-and-verify + mutation gate work end-to-end. Writer/Reviewer pattern, convention learning, and the JS / Python adapters land in subsequent phases.

## What works today

- `autotest --help` / `autotest version` -- top-level CLI.
- `autotest php inventory <path>` -- walk a PHP file or directory, list every public method / function (uses tree-sitter PHP).
- `autotest php generate <path>` -- generate tests, run them via Pest, run the mutation gate (Pest `--mutate`), retry on failure with structured feedback, reject candidates that never pass both checks.
  - `--generator=claude` (default) uses Claude via LiteLLM. Requires `ANTHROPIC_API_KEY`.
  - `--generator=fake` runs the whole pipeline with a deterministic stub generator -- useful for testing the orchestrator without burning tokens.
  - `--dry-run` shows what would be generated without writing or running anything.
  - `--method=<name>` targets a single method.
  - `--mutation-min=N` raises / lowers the MSI threshold (default `60`).
  - `--no-mutation-gate` skips the mutation step (faster, but no guarantee the test catches regressions).

## What's coming

| Phase | Status | Adds |
|---|---|---|
| 0. Skeleton + CI | **Done** | Repo, CLI, AST walker, PHP `inventory`. |
| 1. PHP MVP | **Done** | Generator interface, Claude backend via LiteLLM + Instructor, prompt builder with sibling-test few-shot slots, atomic test writer, subprocess test runner with retry feedback loop. |
| 2. Mutation gate | **Done** | Pest `--mutate` + Infection score parsers, MSI threshold gate, structured "your test passes but doesn't catch mutants -- strengthen the assertions" feedback into retry. |
| 3. Writer/Reviewer | Next | Two-pass LLM pattern for quality. |
| 4. Convention learning | | Sibling-test scanner, project-convention inference. |
| 5. PHP polish | | Budget cap, JSON output, GitHub Action mode. |
| 6. JS / Vue adapter | | `autotest js`, Vitest + Stryker. |
| 7. Python adapter | | `autotest python`, pytest + mutmut. |

## Install

```bash
pipx install simtabi-autotest
```

Or for project-local use:

```bash
# PHP project
composer require --dev simtabi/autotest-php

# JS project
pnpm add -D @simtabi/autotest-js
```

The wrappers transparently delegate to the Python core.

## Usage (Phase 1)

```bash
# Walk a PHP file and list public methods (no LLM, no API key needed)
autotest php inventory src/Services/IconBrowserService.php

# Generate tests with the fake generator (dry-run, no LLM, no test execution)
autotest php generate src/Services/IconBrowserService.php \
    --generator=fake --dry-run

# Generate tests with Claude (requires ANTHROPIC_API_KEY)
export ANTHROPIC_API_KEY=sk-ant-...
autotest php generate src/Services/IconBrowserService.php \
    --project-root . --max-attempts=3

# Target one method only
autotest php generate src/Services/IconBrowserService.php \
    --method=getStatistics
```

## Design (one paragraph)

The pipeline is six stages: **inventory** (tree-sitter AST + coverage report) -> **context** (method body + sibling tests + project conventions) -> **generation** (Claude / Qodo / pluggable) -> **verification** (run the test, retry on failure) -> **quality gate** (mutation testing) -> **commit** (only tests that earned their keep). The orchestrator is language-agnostic; per-language adapters plug in tree-sitter rules and shell commands.

## Why Python (not PHP) for the tool

The code being tested is PHP / JS / Vue / Python. The tool itself is Python because the AI/ML and AST tooling ecosystem (tree-sitter-language-pack, LiteLLM, Instructor, Pydantic) is overwhelmingly Python-first. Qodo Cover and most peers use the same architecture. PHP devs get the familiar entry point via the `simtabi/autotest-php` Composer wrapper.

## License

MIT
