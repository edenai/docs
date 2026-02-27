# Documentation Snippet Tests

Automated test suite that extracts Python code snippets from `.mdx` documentation files and validates them.

## Overview

The docs contain ~229 Python code snippets across ~30 `.mdx` files under `v3/`. This test suite:

1. **Extracts** all Python code blocks from `.mdx` files
2. **Validates syntax** via `ast.parse()` on each individual snippet
3. **Executes** each snippet independently against the Eden AI API (sandbox or production token depending on the endpoint)

## Directory Structure

```
tests/
  conftest.py              # Pytest config, fixture file generation, session setup
  requirements.txt         # Python dependencies
  snippet_extractor.py     # Parses .mdx files, generates importable .py modules
  test_snippets_syntax.py  # Syntax validation (no API key needed)
  test_snippets_execute.py # Execution tests (requires sandbox API key)
  generated/               # Auto-generated .py modules (gitignored)
```

## How It Works

### Snippet Extractor

`snippet_extractor.py` is the core engine. It:

1. Globs all `v3/**/*.mdx` files
2. Extracts fenced Python code blocks (` ```python ... ``` `) using regex
3. Wraps each block in its own function (`block_1()`, `block_2()`, etc.) for independent testing
4. Applies transforms:
   - Replaces `YOUR_API_KEY` / `YOUR_EDEN_AI_API_KEY` / hardcoded API key strings with `os.environ["EDEN_AI_SANDBOX_API_TOKEN"]` (or `EDEN_AI_PRODUCTION_API_TOKEN` for v2 admin endpoints)
   - Replaces hardcoded `https://api.edenai.run` with a configurable `_EDEN_BASE_URL`
   - Adds `import os` at module level
5. Writes to `tests/generated/<module_name>.py`

Each generated module also has a `main()` that calls all block functions in order, so modules can be run standalone.

### Test Fixture Files

`conftest.py` generates minimal valid binary files at test session startup (no binaries stored in git):

- PDF files (~200 bytes): `document.pdf`, `invoice.pdf`
- JPEG files: `image.jpg`, `photo.jpg`, `product.jpg`, `people.jpg`, `passport.jpg`
- PNG file: `image.png`
- Text file: `document.txt`

These are placed in a temp directory used as `cwd` during execution tests, so snippet code like `open("image.jpg", "rb")` works without modification.

### Syntax Tests

`test_snippets_syntax.py` runs `ast.parse()` on each **individual** code block. This catches:

- Indentation errors
- Markdown rendering artifacts (`**name**` instead of `__name__`, `\*\*` instead of `**`)
- Missing colons, unterminated strings, etc.

No API key required — pure static analysis.

### Execution Tests

`test_snippets_execute.py` imports each generated module and calls each block function independently. This validates:

- API calls succeed against the sandbox (or production endpoint for v2 admin snippets)
- Response structures match what the snippet code expects

**Two token types:**
- `EDEN_AI_SANDBOX_API_TOKEN` — used for most snippets (AI feature calls return mock responses, no credits consumed)
- `EDEN_AI_PRODUCTION_API_TOKEN` — used for v2 admin endpoints (cost management, token management); tests are skipped if not set

Each block function is a separate test case, so a failure in one block doesn't prevent other blocks on the same page from running.

For snippets with `input()` calls, `monkeypatch` provides test values automatically.

## Running Tests

### Prerequisites

```bash
# Create a virtual environment
uv venv .venv
source .venv/bin/activate

# Install dependencies
uv pip install -r tests/requirements.txt
```

### Syntax Tests Only (no API key needed)

```bash
pytest tests/test_snippets_syntax.py -v
```

### Full Suite (requires sandbox token)

```bash
EDEN_AI_SANDBOX_API_TOKEN=<your_sandbox_token> pytest tests/ -v
```

### Including v2 Admin Endpoint Tests

```bash
EDEN_AI_SANDBOX_API_TOKEN=<sandbox_token> EDEN_AI_PRODUCTION_API_TOKEN=<real_token> pytest tests/ -v
```

### Run Extractor Standalone

Useful for inspecting what gets generated:

```bash
python tests/snippet_extractor.py
```

Generated modules are written to `tests/generated/` and can be inspected or run individually:

```bash
EDEN_AI_SANDBOX_API_TOKEN=<token> python tests/generated/v3_how_to_universal_ai_text_features.py
```

## CI (GitHub Actions)

The workflow at `.github/workflows/test-snippets.yml` runs on PRs that touch `v3/**/*.mdx` or `tests/**`:

1. **Syntax job**: runs syntax tests (fast, no secrets needed)
2. **Execution job**: runs execution tests with `EDEN_AI_SANDBOX_TOKEN` and `EDEN_AI_PRODUCTION_TOKEN` secrets

To set up: add `EDEN_AI_SANDBOX_TOKEN` and `EDEN_AI_PRODUCTION_TOKEN` as repository secrets in GitHub.

## Adding New Documentation

When adding new `.mdx` files with Python code snippets:

1. Ensure Python code blocks use ` ```python ` fencing
2. Make each snippet self-contained (include its own imports, define `url`, `headers`, etc.)
3. Run `pytest tests/test_snippets_syntax.py -v` to verify syntax
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

## Common Failure Patterns

| Pattern | Cause | Fix |
|---------|-------|-----|
| `IndentationError: expected an indented block` | Code inside a function not indented in the `.mdx` | Add 4-space indent to the code block in the `.mdx` |
| `SyntaxError` with `**name**` | Markdown bold rendering corrupted `__name__` | Use `__name__` (double underscores) inside code fences |
| `SyntaxError` with `\*\*` | Markdown escaped `**` operator | Use `**` (unescaped) inside code fences |
| `unexpected indent` on first line | Extra indentation in the `.mdx` code block | Remove leading whitespace from the code block |
