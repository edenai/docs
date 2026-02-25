# Documentation Snippet Tests

Automated test suite that extracts Python code snippets from `.mdx` documentation files and validates them.

## Overview

The docs contain ~242 Python code snippets across ~30 `.mdx` files under `v3/`. This test suite:

1. **Extracts** all Python code blocks from `.mdx` files
2. **Validates syntax** via `ast.parse()` on each individual snippet
3. **Executes** concatenated per-page snippets against the Eden AI sandbox API

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
3. For each page, concatenates all Python snippets in document order into a single module
4. Wraps the concatenated code in a `def main():` function with an `if __name__` guard
5. Applies transforms:
   - Replaces `YOUR_API_KEY` / `YOUR_EDEN_AI_API_KEY` with `os.environ["EDEN_AI_API_KEY"]`
   - Deduplicates import statements across snippets on the same page
   - Adds `import os` if not present
6. Writes to `tests/generated/<module_name>.py`

The generated files are importable Python modules that can also be run standalone.

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

`test_snippets_execute.py` imports the generated modules and calls `main()` in-process. This validates:

- API calls succeed against the sandbox
- Response structures match what the snippet code expects
- Variable dependencies between snippets on the same page work correctly

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
EDEN_AI_API_KEY=<your_sandbox_token> pytest tests/ -v
```

### Run Extractor Standalone

Useful for inspecting what gets generated:

```bash
python tests/snippet_extractor.py
```

Generated modules are written to `tests/generated/` and can be inspected or run individually:

```bash
EDEN_AI_API_KEY=<token> python tests/generated/v3_how_to_universal_ai_text_features.py
```

## CI (GitHub Actions)

The workflow at `.github/workflows/test-snippets.yml` runs on PRs that touch `v3/**/*.mdx` or `tests/**`:

1. **Syntax job**: runs syntax tests (fast, no secrets needed)
2. **Execution job**: runs execution tests with `EDEN_AI_SANDBOX_TOKEN` secret

To set up: add `EDEN_AI_SANDBOX_TOKEN` as a repository secret in GitHub.

## Adding New Documentation

When adding new `.mdx` files with Python code snippets:

1. Ensure Python code blocks use ` ```python ` fencing
2. First snippet on a page should define `url` and `headers` if later snippets depend on them
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
