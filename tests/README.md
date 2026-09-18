# Documentation Snippet Tests

Automated test suite that extracts code snippets from `.mdx` documentation files and executes them against the Eden AI API. Python snippets become importable modules; shell snippets become scripts and are run with bash, so what gets tested is the command a reader would paste.

## Setup

```bash
# Create a virtual environment
uv venv .venv
source .venv/bin/activate

# Install dependencies
uv pip install -r tests/requirements.txt

# The Ask AI eval pipeline (tests/evals/) has its own file, which includes the above
uv pip install -r tests/requirements-evals.txt

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
| `EDEN_AI_BASE_URL` | Optional | Defaults to `https://staging-api.edenai.run`. CI runs against production. The integration guides that drive Eden AI through a framework holding a hardcoded production endpoint (Haystack) are reported as skipped anywhere else |
| `EDEN_AI_RUN_PAID_CALLS` | Optional | Off by default, so neither a docs PR nor a local run bills the account. Set to `1` to also run the samples marked `{/* paid-test */}`, which need the model to answer for real. CI turns it on for the weekly run and for a manual dispatch, never for a pull request |
| `EDENAI_API_KEY` | Set for you | Not something you fill in: the suite publishes the token above under this name because the integration frameworks (any-llm, Haystack, Atomic Agents) read the key from the environment rather than taking it as an argument |

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
   - Use `YOUR_API_KEY` as the inference key placeholder, `YOUR_MANAGEMENT_KEY` for Management API (`/v3/manage/...`) calls, and `YOUR_SANDBOX_TOKEN` where the page is specifically about sandbox tokens; the extractor swaps each for the matching environment variable
3. Run `pytest tests/ -v` to verify
4. The extractor auto-discovers new `.mdx` files (under `v3/` and at the repo root) — no configuration needed

### Shell Snippets

The curl samples are what most readers copy, so they run too. Each block
becomes a script under `tests/generated/sh/` and is run with bash. The command
itself is never rewritten; the script wraps it in shims:

- `curl` gains `--fail-with-body`, because curl exits 0 on a 4xx or 5xx and a
  retired endpoint would otherwise pass in silence.
- `pip` and `npm` gain `--dry-run`, so an install block resolves the package
  against its index and lands nothing in the runner's environment.

Two kinds of block run: a curl call to Eden AI, and a plain install. Everything
else on a page is left alone and never becomes a script, because running it
would drive somebody else's software (`docker compose up`, `git clone`, an
admin password reset). That rule lives in `_is_testable_shell`, and
`tests/test_snippet_extractor.py` asserts no generated script can touch local
state.

Placeholders resolve the same way they do in Python (`YOUR_API_KEY`,
`YOUR_MANAGEMENT_KEY`, `YOUR_SANDBOX_TOKEN`, `YOUR_FILE_UUID_OR_URL`). Almost
every curl body is `-d '{...}'` and the shell expands nothing inside single
quotes, so a placeholder there is spliced as `'"$VAR"'`. The run uploads a
document and an image, and a sample gets whichever its model calls for: an
image model rejects a PDF outright.

### Skipping Non-Runnable Snippets

The same `{/* skip-test */}` and `{/* paid-test */}` markers work for shell blocks. A marker above a `<CodeGroup>` covers every fence in the group, and a marker directly above one fence covers only that fence.

Some ` ```python ` blocks are illustrative fragments (e.g., `"model": "openai/gpt-4o"`) rather than valid standalone Python, and a few depend on something no test environment can supply (a package that has not shipped the code the page documents, a module that only exists inside another project's tree). To exclude a block from testing while preserving syntax highlighting, add an MDX comment before the fence:

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

The marker carries the reason, and every marker in the docs has one. It is what
stops the next person re-deciding from scratch whether the block should run:

```
{/* skip-test: the Eden AI provider is merged upstream but not in any aisuite release yet */}
```

The comment is invisible in rendered docs. The extractor checks the 3 lines preceding each ` ```python ` fence for the marker. A fence is a fence whatever tab label follows the language (` ```python OpenAI SDK `) and whatever indentation it sits at inside a `<Step>` or `<Accordion>`, so a block cannot escape the suite by being nested or labelled. Skipped blocks still appear in test output (as `SKIPPED`) rather than being silently excluded, so you can track how many snippets are skipped.

### Snippets That Need a Real Model Answer

The sandbox token serves one canned text completion. That carries any sample
which only reads the message content, but not one that asks the model for
structure: a JSON schema response, a pydantic `output_type`, an Instructor tool
call. Those need a production token and a real inference call, which costs
credits every time it runs.

Mark them, in the same place and the same shape as `skip-test`:

```
{/* paid-test: needs a real model answer, the sandbox returns canned prose */}
```

The marker does two things. It switches that one block to
`EDEN_AI_PRODUCTION_API_TOKEN`, whatever the rest of the page uses, and it holds
the block back unless `EDEN_AI_RUN_PAID_CALLS` is set. So a docs PR and a local
run report it as `SKIPPED` and spend nothing, and the weekly scheduled run
executes it.

Reach for this only when the sandbox genuinely cannot serve the sample. It buys
coverage with money, so a block that would pass on the sandbox should not carry
it.

## CI (GitHub Actions)

The workflow at `.github/workflows/test-snippets.yml` runs on PRs that touch `v3/**/*.mdx` or `tests/**`:

1. **Check snippet syntax**: parses every extracted snippet, Python and shell, with no credentials and no API calls, so it still reports a broken snippet on a run where the secrets are missing
2. **Run Python snippets** and **Run shell snippets**: execution tests with the `EDEN_AI_SANDBOX_TOKEN`, `EDEN_AI_PRODUCTION_TOKEN` and `EDEN_AI_MANAGEMENT_KEY` secrets

It also runs weekly, Mondays at 06:00 UTC against `main`, because the docs go
stale against a moving API even when nobody edits them. The weekly run is the
only scheduled one that sets `EDEN_AI_RUN_PAID_CALLS`, so the `paid-test`
samples get their coverage there rather than on every pull request. A manual
dispatch sets it too.

Installs from `requirements-lock.txt` for reproducible builds.

To set up: add `EDEN_AI_SANDBOX_TOKEN`, `EDEN_AI_PRODUCTION_TOKEN` and `EDEN_AI_MANAGEMENT_KEY` as repository secrets in GitHub. Without `EDEN_AI_MANAGEMENT_KEY` the Management API samples are reported as skipped, not failed.

## Common Failure Patterns

| Pattern | Cause | Fix |
|---------|-------|-----|
| `IndentationError: expected an indented block` | Code inside a function not indented in the `.mdx` | Add 4-space indent to the code block in the `.mdx` |
| `SyntaxError` with `**name**` | Markdown bold rendering corrupted `__name__` | Use `__name__` (double underscores) inside code fences |
| `SyntaxError` with `\*\*` | Markdown escaped `**` operator | Use `**` (unescaped) inside code fences |
| `unexpected indent` on first line | Extra indentation in the `.mdx` code block | Remove leading whitespace from the code block |
