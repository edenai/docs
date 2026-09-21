# Claude Code Project Context

## Project Overview

This is the Eden AI documentation site, built with [Mintlify](https://mintlify.com). The docs cover Eden AI's V3 API which provides access to 200+ AI models through a unified interface.

See `README.md` for repository structure, local development setup, and publishing workflow.

## Key Conventions

- Documentation files are `.mdx` (MDX = Markdown + JSX)
- Code snippets are inline in `.mdx` files using `<CodeGroup>` for multi-language tabs
- API endpoints: `https://api.edenai.run/v3/...` (LLM) and `https://api.edenai.run/v3/universal-ai` (Universal AI)
- Auth: `Authorization: Bearer <api_key>`
- Model format: `provider/model` for LLM, `feature/subfeature/provider[/model]` for Universal AI
- Token types: `api_token` (production) and `sandbox_api_token` (testing, no real provider calls)

## Working with Documentation Snippets

All Python snippets in the docs (under `v3/` and at the repo root) are automatically tested, and so are the curl and install commands in ` ```bash ` blocks and the samples in ` ```javascript ` and ` ```typescript ` blocks. See `tests/README.md` for setup, running tests, and how to test specific pages.

- To inspect extracted snippets for a page, read the corresponding file in `tests/generated/` (e.g. `tests/generated/v3_how_to_discovery_explore_api.py` for `v3/how-to/discovery/explore-api.mdx`; shell blocks land in `tests/generated/sh/`, JS and TS in `tests/generated/js/`). Do NOT run the extractor or custom Python scripts — just read the generated file directly.
- When a snippet test fails, **fix the snippet code** (add missing imports, correct logic, etc.) and if needed add dependencies to `tests/requirements.txt`. Do NOT use `{/* skip-test */}` to silence a fixable test failure — `skip-test` is only for genuinely non-runnable fragments, and every marker in the docs carries its reason as `{/* skip-test: why */}`, so write one.
- If a snippet fails only because the sandbox returns canned prose where the sample needs the model to answer for real (JSON schema output, a pydantic `output_type`, an Instructor tool call), mark it `{/* paid-test: reason */}` rather than `skip-test`. That block then uses the production token and runs in the weekly CI run, not on every PR.
- Every generated module is syntax-checked by `tests/test_snippets_compile.py`, including blocks that never execute, so a skipped snippet still cannot contain invalid Python, bash or JavaScript. The TypeScript blocks are type-checked there too, against the real SDK typings.
- A shell block runs only if it is a curl call to Eden AI or a plain `pip`/`npm` install. Anything that drives other software (docker, git clone) is never turned into a script. Do NOT add such a command expecting it to be tested.
- A JS or TS block runs only if node can run it: every import must be a node builtin or a package listed in `tests/package.json`. A block importing anything else (a React component, an Express receiver) is reported as SKIPPED with the reason naming the package, not dropped. If a new sample needs a package, add it to `tests/package.json` (pinned) and commit the refreshed lockfile; the allowlist is read from that file. A block node cannot run for a reason no import shows, such as reading from a browser `<input>`, needs a `{/* skip-test: why */}` marker like any other.
- TypeScript samples must use erasable syntax only, because node runs them by stripping the annotations out. No `enum`, no `namespace`, no parameter properties: `tsc` rejects them so the sample cannot ship broken.
- Skipped blocks still appear in test output (as `SKIPPED`) so the total snippet count stays visible. Failed tests include HTTP request/response details automatically.

## Links

Every link on every published page is checked by `tests/test_links.py`, which reads files and makes no requests. See `tests/README.md` for the details.

- A link to a page that does not exist fails the build, as does an anchor naming a heading the target page does not have. Anchors follow github-slugger: `## Extended Thinking (Claude)` is `#extended-thinking-claude`.
- Renaming or deleting a page means updating `docs.json` and every page that links to it. A page that ends up in neither the navigation nor any other page's links fails the reachability check, because nobody can reach it.
- `#chat` and `#manage-cookies` are click targets bound by `intercom-chat.js` and `cookie-consent.js`, not headings. They are allowlisted in `tests/links.py`, and a test confirms each is really bound. Do NOT add an entry there to silence a broken anchor.
- Links inside code fences are examples, not links, and are ignored. Do not rely on that to park a link that does not resolve.
- The links that leave the docs, and the two OpenAPI specs the API reference tabs render from, are in `tests/test_links_external.py`. The specs are checked on every run; the third-party links only on the weekly one, since they depend on somebody else's site being up.

## Common Pitfalls in .mdx Code Blocks

- Double underscores (`__name__`) can render as bold in some contexts — always verify inside code fences
- The `**` operator can be escaped to `\*\*` by some editors — keep it as `**` inside code fences
- Code inside function definitions must be indented (some snippets in the repo have had this bug)
- Snippets later on a page may depend on `url`/`headers` defined in earlier snippets

## Eval Pipeline (tests/evals/)

Evaluation pipeline for Mintlify Ask AI answer quality. Failures identify documentation improvements — we control the docs, not the LLM.

- **21 test questions** in `tests/evals/dataset.json` organized by `category` and `difficulty`
- **3 metrics**: RetrievalAccuracy (did Mintlify find the right page?), AnswerRelevancy (did it answer the question?), ContextualRecall (does the doc have the info?)
- **Filtering**: `--category=llm`, `--difficulty=advanced`
- **Run**: `pytest tests/evals/ -n0` (requires `EDEN_AI_PRODUCTION_API_TOKEN`; first run also needs `MINTLIFY_API_KEY`)
- Answers + retrieved paths are cached in `tests/evals/.cache/answers.json`; use `--refresh-answers` to re-fetch
- See `tests/evals/README.md` for full setup and usage

## Linear Issue Tracking

- Team: Eden AI Platform
- Current sprint work tracked via Linear (EDE3-xxx identifiers)
- Git branches follow pattern: `username/ede3-xxx-description`
