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
| `EDEN_AI_PRODUCTION_API_TOKEN` | Optional | Production token, needed by the few pages whose samples require real provider responses (e.g. structured output); skipped if not set |
| `EDEN_AI_MANAGEMENT_KEY` | Optional | Management key (`mgmt-eden-...`, `manage:read` + `manage:write`), needed by Management API samples (custom API keys, sandbox key creation, monitoring). Samples mint real inference keys in the key's organization; the run revokes them on the way out, and clears any left by a cancelled run before it starts. Cleanup only ever touches keys named after the samples (`production-v1`, `team-backend`, `team-daily`, `dev-testing`). Skipped if not set |
| `EDEN_AI_BASE_URL` | Optional | Defaults to `https://staging-api.edenai.run` |

## Running Tests

```bash
pytest tests/ -v
```

Tests run in parallel by default (via `pytest-xdist`, configured in `pytest.ini` with `-n auto` which matches the CPU count). Each test is capped at 5 minutes (`pytest-timeout`), every `requests` call made by a snippet gets a 120-second timeout unless it sets its own, and 429 retries wait at most 30 seconds, so a request the API never answers fails with its details instead of stalling the run. Override the worker count with `-n`:

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
   - Use `YOUR_API_KEY` as the inference key placeholder and `YOUR_MANAGEMENT_KEY` for Management API (`/v3/manage/...`) calls; the extractor swaps each for the matching environment variable
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


## Model Reference Checks

`test_model_references.py` checks every model the docs name against the live
catalogue, so a page cannot keep recommending an id the API has dropped. It
covers both naming schemes:

* LLM ids (`anthropic/claude-sonnet-5`), against the seven `/v3/**/models`
  listings. `/v3/models` alone is chat-only, so checking just that one reports
  every embedding, image, audio and video model as missing.
* expert-model paths (`image/explicit_content/amazon`), against `/v3/info`.

Both endpoints are public, so these tests need no credentials and cost nothing.
CI runs them as their own step, before the snippet tests, so a stale model id
is still reported on a run where the API secrets are missing. They currently
validate a bit over 400 references.

A failure names the page, the line and the live alternatives:

```
v3/llms/image-generation.mdx names 1 model(s) the API does not have:
  line 49: google/imagen-4.0-generate-001
      closest ids: google/imagen-4.0-fast-generate-001, google/imagen-4.0-ultra-generate-001
```

Only backticked fragments that could be an id verbatim are checked. Anything
holding placeholder or wildcard syntax documents a shape rather than naming a
model (`audio/tts/{provider}[/{model}]`, `anthropic/*`) and is skipped, as is a
bare `feature/subfeature`, which names a route.

Known gaps, so nobody reads a green run as more than it is. A fragment is only
checked when its first segment is a known feature or a known LLM provider, so
a misspelt provider (`anthropc/claude-sonnet-5`) reads as an unknown namespace
and passes, and ids carrying an integration's own prefix
(`edenai:anthropic/claude-sonnet-5` on the aisuite page, `edenai/openai/gpt-5.5`
on the bifrost page) are not checked either. Closing those needs a way to tell
a model id from any other slash-separated word in prose, which a backtick alone
does not give.

## CI (GitHub Actions)

The workflow at `.github/workflows/test-snippets.yml` runs on PRs that touch `v3/**/*.mdx` or `tests/**`:

1. **Execution job**: runs execution tests with the `EDEN_AI_SANDBOX_TOKEN`, `EDEN_AI_PRODUCTION_TOKEN` and `EDEN_AI_MANAGEMENT_KEY` secrets

Installs from `requirements-lock.txt` for reproducible builds.

To set up: add `EDEN_AI_SANDBOX_TOKEN`, `EDEN_AI_PRODUCTION_TOKEN` and `EDEN_AI_MANAGEMENT_KEY` as repository secrets in GitHub. Without `EDEN_AI_MANAGEMENT_KEY` the Management API samples are reported as skipped, not failed.

## Common Failure Patterns

| Pattern | Cause | Fix |
|---------|-------|-----|
| `IndentationError: expected an indented block` | Code inside a function not indented in the `.mdx` | Add 4-space indent to the code block in the `.mdx` |
| `SyntaxError` with `**name**` | Markdown bold rendering corrupted `__name__` | Use `__name__` (double underscores) inside code fences |
| `SyntaxError` with `\*\*` | Markdown escaped `**` operator | Use `**` (unescaped) inside code fences |
| `unexpected indent` on first line | Extra indentation in the `.mdx` code block | Remove leading whitespace from the code block |
