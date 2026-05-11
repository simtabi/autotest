# simtabi-autotest

> AI-driven test generation with a **mutation-testing quality gate**. Tests that don't kill mutants don't ship.

Mass-generated AI tests are easy to produce and just as easy to pad coverage with — but coverage going up while real bugs slip through is the well-documented failure mode in 2026. `simtabi-autotest` short-circuits that by treating every generated test as a hypothesis and using mutation testing as the verifier: if your generated test can't detect a mutated version of the function under test, the test is rejected before it ever lands in your tree.

## Status

**Alpha (Phase 0 / 7).** Skeleton + PHP adapter inventory works end-to-end. Generation, verification, and mutation gate land in subsequent phases. Track progress in [PLAN.md](PLAN.md).

## What works today

- `autotest --help` -- top-level CLI.
- `autotest version` -- show installed version.
- `autotest php inventory <path>` -- walk a PHP file or directory, list every public method / function (uses tree-sitter PHP).

## What's coming

| Phase | Status | Adds |
|---|---|---|
| 0. Skeleton + CI | **Now** | Repo, CLI, AST walker, PHP `inventory`. |
| 1. PHP MVP | Next | `autotest php generate` end-to-end with Claude. |
| 2. Mutation gate | | Pest `--mutate` + Infection wired in. Tests below MSI threshold are rejected. |
| 3. Writer/Reviewer | | Two-pass LLM pattern for quality. |
| 4. Convention learning | | Few-shot from sibling tests. |
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

## Usage (Phase 0)

```bash
# Walk a PHP file and list public methods
autotest php inventory src/Services/IconBrowserService.php

# Walk a whole directory
autotest php inventory src/
```

## Design (one paragraph)

The pipeline is six stages: **inventory** (tree-sitter AST + coverage report) -> **context** (method body + sibling tests + project conventions) -> **generation** (Claude / Qodo / pluggable) -> **verification** (run the test, retry on failure) -> **quality gate** (mutation testing) -> **commit** (only tests that earned their keep). The orchestrator is language-agnostic; per-language adapters plug in tree-sitter rules and shell commands.

## Why Python (not PHP) for the tool

The code being tested is PHP / JS / Vue / Python. The tool itself is Python because the AI/ML and AST tooling ecosystem (tree-sitter-language-pack, LiteLLM, Instructor, Pydantic) is overwhelmingly Python-first. Qodo Cover and most peers use the same architecture. PHP devs get the familiar entry point via the `simtabi/autotest-php` Composer wrapper.

## License

MIT
