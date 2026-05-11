"""autotest: AI-driven test generation with a mutation-testing quality gate.

Why this exists:

- Mass-produced AI tests are easy to generate and easy to pad coverage with;
  the hard part is generating tests that catch real regressions.
- We solve that with a two-pass pipeline: LLM writes the test, then a
  mutation test runner verifies the test actually kills mutants in the code
  under test. Tests that don't earn their keep are rejected before they
  reach disk.

The orchestration is language-agnostic; per-language adapters (PHP, JS/TS,
Vue, Python) plug in the actual AST walker, test runner, and mutation tool.
"""

__version__ = "0.1.0"
