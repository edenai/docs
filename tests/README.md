# Documentation Snippet Tests

Automated test suite that extracts Python code snippets from `.mdx` documentation files, validates syntax, lints for missing imports, and executes them against the Eden AI API.

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

### Syntax only (no API key needed)

```bash
pytest tests/test_snippets_syntax.py -v
```

### Ruff lint only (no API key needed)

Checks for undefined names / missing imports (ruff F821):

```bash
pytest tests/test_snippets_ruff.py -v
```

### Execution tests (requires sandbox token)

```bash
pytest tests/test_snippets_execute.py -v
```

### Full suite

```bash
pytest tests/ -v
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

You can also run a generated module standalone:

```bash
python tests/generated/v3_how_to_universal_ai_text_features.py
```

### Inspect what gets extracted

```bash
python tests/snippet_extractor.py
```

## Adding New Documentation

When adding new `.mdx` files with Python code snippets:

1. Use ` ```python ` fencing for code blocks
2. Make each snippet self-contained (include its own imports, define `url`, `headers`, etc.)
3. Run `pytest tests/test_snippets_syntax.py tests/test_snippets_ruff.py -v` to verify
4. The extractor auto-discovers new `.mdx` files — no configuration needed

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

The comment is invisible in rendered docs. The extractor checks the 3 lines preceding each ` ```python ` fence for the marker.

## CI (GitHub Actions)

The workflow at `.github/workflows/test-snippets.yml` runs on PRs that touch `v3/**/*.mdx` or `tests/**`:

1. **Syntax job**: runs syntax tests (fast, no secrets needed)
2. **Execution job**: runs execution tests with `EDEN_AI_SANDBOX_TOKEN` and `EDEN_AI_PRODUCTION_TOKEN` secrets

Both jobs install from `requirements-lock.txt` for reproducible builds.

To set up: add `EDEN_AI_SANDBOX_TOKEN` and `EDEN_AI_PRODUCTION_TOKEN` as repository secrets in GitHub.

## Common Failure Patterns

| Pattern | Cause | Fix |
|---------|-------|-----|
| `IndentationError: expected an indented block` | Code inside a function not indented in the `.mdx` | Add 4-space indent to the code block in the `.mdx` |
| `SyntaxError` with `**name**` | Markdown bold rendering corrupted `__name__` | Use `__name__` (double underscores) inside code fences |
| `SyntaxError` with `\*\*` | Markdown escaped `**` operator | Use `**` (unescaped) inside code fences |
| `unexpected indent` on first line | Extra indentation in the `.mdx` code block | Remove leading whitespace from the code block |
