# Claude Code Project Context

## Project Overview

This is the Eden AI documentation site, built with [Mintlify](https://mintlify.com). The docs cover Eden AI's V3 API which provides access to 200+ AI models through a unified interface.

## Repository Structure

```
v3/                          # V3 API documentation (primary)
  get-started/               # Intro, FAQ, enterprise, professional services
  how-to/                    # Guides: authentication, cost-management, discovery, llm, router, universal-ai, upload, user-management
  integrations/              # SDKs, frameworks (langchain), AI assistants, chat platforms
  tutorials/                 # Multi-step tutorials
  changelog.mdx              # Changelog
  llms.txt                   # LLM-friendly plain-text docs
api-reference/               # API reference pages
openapi/                     # OpenAPI spec files
tests/                       # Automated snippet test suite
  snippet_extractor.py       # Extracts Python snippets from .mdx -> importable .py modules
  test_snippets_syntax.py    # ast.parse() validation (no API key needed)
  test_snippets_ruff.py      # Ruff lint tests — detects undefined names (F821)
  test_snippets_execute.py   # In-process execution with sandbox token
  conftest.py                # Fixture generation, file upload/cleanup, custom token cleanup, HTTP recorder
  requirements.txt           # Python dependencies
  requirements-lock.txt      # Pinned dependency versions (used by CI)
  generated/                 # Auto-generated modules (gitignored)
.github/workflows/
  test-snippets.yml          # CI: syntax + execution tests on PR
```

## Key Conventions

- Documentation files are `.mdx` (MDX = Markdown + JSX)
- Code snippets are inline in `.mdx` files using `<CodeGroup>` for multi-language tabs
- API endpoints: `https://api.edenai.run/v3/llm/...` (LLM) and `https://api.edenai.run/v3/universal-ai` (Universal AI)
- Auth: `Authorization: Bearer <api_key>`
- Model format: `provider/model` for LLM, `feature/subfeature/provider[/model]` for Universal AI
- Token types: `api_token` (production) and `sandbox_api_token` (testing, no real provider calls)

## Working with Documentation Snippets

- All Python snippets in the docs are automatically tested by the suite in `tests/`
- Run `pytest tests/test_snippets_syntax.py -v` to check syntax after editing any `.mdx` file
- Run `pytest tests/test_snippets_ruff.py -v` to check for undefined names (missing imports) via ruff
- Run `python tests/snippet_extractor.py` to see extraction results
- To inspect extracted snippets for a page, read the corresponding file in `tests/generated/` (e.g. `tests/generated/v3_how_to_discovery_explore_api.py` for `v3/how-to/discovery/explore-api.mdx`). Do NOT run the extractor or custom Python scripts — just read the generated file directly.
- See `tests/README.md` for full details on the test infrastructure

## Common Pitfalls in .mdx Code Blocks

- Double underscores (`__name__`) can render as bold in some contexts — always verify inside code fences
- The `**` operator can be escaped to `\*\*` by some editors — keep it as `**` inside code fences
- Code inside function definitions must be indented (some snippets in the repo have had this bug)
- Snippets later on a page may depend on `url`/`headers` defined in earlier snippets
- Non-runnable Python fragments (dict entries, prompt strings) should be marked with `{/* skip-test */}` on the line before the ` ```python ` fence (or before `<CodeGroup>`) to exclude them from testing while preserving syntax highlighting
- When a snippet test fails, **fix the snippet code** (add missing imports, correct logic, etc.) and if needed add dependencies to `tests/requirements.txt`. Do NOT use `{/* skip-test */}` to silence a fixable test failure — `skip-test` is only for genuinely non-runnable fragments

## Linear Issue Tracking

- Team: Eden AI Platform
- Current sprint work tracked via Linear (EDE3-xxx identifiers)
- Git branches follow pattern: `username/ede3-xxx-description`
