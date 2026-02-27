# Claude Code Project Context

## Project Overview

This is the Eden AI documentation site, built with [Mintlify](https://mintlify.com). The docs cover Eden AI's V3 API which provides access to 200+ AI models through a unified interface.

See `README.md` for repository structure, local development setup, and publishing workflow.

## Key Conventions

- Documentation files are `.mdx` (MDX = Markdown + JSX)
- Code snippets are inline in `.mdx` files using `<CodeGroup>` for multi-language tabs
- API endpoints: `https://api.edenai.run/v3/llm/...` (LLM) and `https://api.edenai.run/v3/universal-ai` (Universal AI)
- Auth: `Authorization: Bearer <api_key>`
- Model format: `provider/model` for LLM, `feature/subfeature/provider[/model]` for Universal AI
- Token types: `api_token` (production) and `sandbox_api_token` (testing, no real provider calls)

## Working with Documentation Snippets

All Python snippets in the docs are automatically tested. See `tests/README.md` for setup, running tests, and how to test specific pages.

- To inspect extracted snippets for a page, read the corresponding file in `tests/generated/` (e.g. `tests/generated/v3_how_to_discovery_explore_api.py` for `v3/how-to/discovery/explore-api.mdx`). Do NOT run the extractor or custom Python scripts — just read the generated file directly.
- When a snippet test fails, **fix the snippet code** (add missing imports, correct logic, etc.) and if needed add dependencies to `tests/requirements.txt`. Do NOT use `{/* skip-test */}` to silence a fixable test failure — `skip-test` is only for genuinely non-runnable fragments.

## Common Pitfalls in .mdx Code Blocks

- Double underscores (`__name__`) can render as bold in some contexts — always verify inside code fences
- The `**` operator can be escaped to `\*\*` by some editors — keep it as `**` inside code fences
- Code inside function definitions must be indented (some snippets in the repo have had this bug)
- Snippets later on a page may depend on `url`/`headers` defined in earlier snippets

## Linear Issue Tracking

- Team: Eden AI Platform
- Current sprint work tracked via Linear (EDE3-xxx identifiers)
- Git branches follow pattern: `username/ede3-xxx-description`
