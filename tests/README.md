# Documentation Snippet Tests

Automated test suite that extracts Python code snippets from `.mdx` documentation files and executes them against the Eden AI API.

## Setup

```bash
# Create a virtual environment
uv venv .venv
source .venv/bin/activate

# Install dependencies
uv pip install -r tests/requirements.txt

# Set up environment variables
cp tests/.env.example tests/.env
# Edit tests/.env and fill in your token values
```

**Environment variables:**

| Variable | Required | Description |
|----------|----------|-------------|
| `EDEN_AI_SANDBOX_API_TOKEN` | For execution tests | Sandbox token — AI features return mock responses, no credits consumed |
| `EDEN_AI_PRODUCTION_API_TOKEN` | Optional | Production token — needed for v2 admin endpoint tests (cost/token management); skipped if not set |
| `EDEN_AI_BASE_URL` | Optional | Defaults to `https://staging-api.edenai.run` |

## Running Tests

```bash
pytest tests/ -v
```

Tests run in parallel by default (via `pytest-xdist`, configured in `pytest.ini` with `-n auto` which matches the CPU count). Override with `-n`:

```bash
pytest tests/ -v -n 5   # 5 workers
pytest tests/ -v -n 0   # disable parallelism
```

### Tests for a specific doc page

Each `.mdx` file maps to a generated module in `tests/generated/`. The naming convention is path separators become `_` and hyphens become `_`:

```
v3/how-to/universal-ai/text-features.mdx -> tests/generated/v3_how_to_universal_ai_text_features.py
```

To run tests for a single page, use pytest's `-k` filter:

```bash
# All tests for text-features.mdx
pytest tests/ -v -k "text_features"

# A specific block (block_3) from that page
pytest tests/ -v -k "text_features and block_3"
```

### Coverage Report

Coverage is enabled by default (via `tests/pytest.ini`). Every `pytest tests/` run prints a coverage summary showing which snippet lines executed.

```bash
# HTML report (opens in browser)
pytest tests/ --cov-report=html
open tests/htmlcov/index.html
```

Coverage measures the generated snippet modules (`tests/generated/`), showing which documentation code blocks actually executed.

### Debugging in VSCode

A launch configuration is included in `.vscode/launch.json`. Use the **"Debug Snippet Tests"** configuration to run tests with the debugger attached — set breakpoints in generated modules or test infrastructure as needed.

### Inspect what gets extracted

```bash
python tests/snippet_extractor.py
```

## Adding New Documentation

When adding new `.mdx` files with Python code snippets:

1. Use ` ```python ` fencing for code blocks
2. Make each snippet self-contained (include its own imports, define `url`, `headers`, etc.)
3. Run `pytest tests/ -v` to verify
4. The extractor auto-discovers new `.mdx` files (under `v3/` and at the repo root) — no configuration needed

### Skipping Non-Runnable Snippets

Some ` ```python ` blocks are illustrative fragments (e.g., `"model": "openai/gpt-4o"`) rather than valid standalone Python. To exclude a block from testing while preserving syntax highlighting, add an MDX comment before the fence:

```
{/* skip-test */}
```python
"model": "openai/gpt-4o"
```​
```

This also works with `<CodeGroup>` blocks — place the comment before the `<CodeGroup>` tag:

```
{/* skip-test */}
<CodeGroup>
```python Python
# code with known issues...
```​
</CodeGroup>
```

The comment is invisible in rendered docs. The extractor checks the 3 lines preceding each ` ```python ` fence for the marker. Skipped blocks still appear in test output (as `SKIPPED`) rather than being silently excluded, so you can track how many snippets are skipped.


## TypeScript snippets

Guides that ship TypeScript examples (`v3/integrations/openai-sdk-typescript.mdx`, `langchain.mdx`, `pi.mdx`) go through a parallel bun-native runner in `tests/ts/`.

```bash
# One-time install
bun install --cwd tests/ts

# Run all TS snippets (bunfig.toml preload script auto-invokes the Python extractor first)
cd tests/ts && bun test
```

Same skip/fixtures mechanics as Python: `{/* skip-test */}` in the `.mdx` produces a `.skip.<ext>` filename that `bun:test` routes to `test.skip`. `tests/generated_ts/fixtures/` is populated via the shared `populate_fixtures_dir()` helper so `image.jpg`, `document.pdf`, etc. are present.

## Validators

Beyond snippet execution, four validators enforce doc/API consistency. All run under the same `pytest -n auto`.

| File | Checks |
|------|--------|
| `tests/config_validator.py` | Parses fenced JSON/YAML/TOML config blocks in tool-integration guides; validates Eden AI URL hosts + endpoint prefixes; cross-checks every `` `provider/model` `` string against the live inventory |
| `tests/api_reference_validator.py` | Fetches the 3 remote OpenAPI specs referenced in `docs.json`, asserts they're reachable and valid, cross-checks every `https://api.edenai.run/v[23]/…` URL in prose against the specs |
| `tests/model_provider_validator.py` | Scans every `.mdx` for backticked `provider/model` references; cross-checks against `/v3/models` + `/v3/info` + probed embeddings inventory |
| `tests/link_checker.py` | Extracts markdown links, JSX `href="…"`, `<TechArticleSchema path="…">`, and bare URLs; verifies internal targets exist and external URLs return 2xx-3xx (or a non-404/410 4xx). Also checks every `docs.json` nav path resolves to an `.mdx` file |

Model/provider lookup is powered by `tests/helpers/edenai_inventory.py` — a session-cached inventory of LLM models (`/v3/models`), expert models (`/v3/info`), and verified embeddings.

Unknown `provider/model` references fail the test unless they match `DOCUMENTATION_PLACEHOLDERS` (e.g. `provider/model` used as a format placeholder) or an `UNAMBIGUOUS_MIME_PREFIXES` prefix (e.g. `application/json`). There is no per-file allowlist.

## CI (GitHub Actions)

The workflow at `.github/workflows/test-snippets.yml` runs on:
- PRs that touch `v3/**/*.mdx`, root `*.mdx`, `docs.json`, or `tests/**`
- Weekly cron (`0 6 * * 1`)
- Manual dispatch

Two jobs, both with `cancel-in-progress: false` (session cleanup runs at pytest_sessionfinish; cancelling a started run orphans account resources):

1. **Python Tests** — snippet execution + all four validators.
2. **TypeScript Tests** — installs bun + runs `bun test` in `tests/ts/`.

Both consume `EDEN_AI_SANDBOX_TOKEN` and (Python job only) `EDEN_AI_PRODUCTION_TOKEN` from repository secrets. `EDEN_AI_BASE_URL` is set from the `EDEN_AI_BASE_URL` repository variable if defined (defaults to staging).

Python deps install from `requirements-lock.txt` for reproducibility. TS deps install from `tests/ts/bun.lock`.

## Disabling the doc-tests workflow

If the docs need to ship despite a failing test run (broken external link, upstream API drift, etc.), disable via GitHub UI: **Actions → Test Documentation Snippets → ⋯ → Disable workflow**. Mintlify's own build pipeline is independent, so the site continues to publish.

## Common Failure Patterns

| Pattern | Cause | Fix |
|---------|-------|-----|
| `IndentationError: expected an indented block` | Code inside a function not indented in the `.mdx` | Add 4-space indent to the code block in the `.mdx` |
| `SyntaxError` with `**name**` | Markdown bold rendering corrupted `__name__` | Use `__name__` (double underscores) inside code fences |
| `SyntaxError` with `\*\*` | Markdown escaped `**` operator | Use `**` (unescaped) inside code fences |
| `unexpected indent` on first line | Extra indentation in the `.mdx` code block | Remove leading whitespace from the code block |
