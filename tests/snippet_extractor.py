"""Extract Python code snippets from .mdx documentation files.

Parses all v3/**/*.mdx files, extracts Python code blocks in document order,
and generates importable .py modules with one function per block for
independent testing.
"""

import re
from pathlib import Path

# Regex to match fenced Python code blocks: ```python [Label]\n...code...\n```
# The closing fence may have leading whitespace (common in the docs).
CODE_BLOCK_RE = re.compile(
    r"^```python(?:[ \t]+\S+)?[ \t]*\n(.*?)^\s*```",
    re.MULTILINE | re.DOTALL,
)

# MDX comment that marks a code block to be skipped by the test suite.
# Place {/* skip-test */} before the ```python fence (or before <CodeGroup>).
_SKIP_COMMENT_RE = re.compile(r"\{/\*\s*skip-test\s*\*/\}")

# ---------------------------------------------------------------------------
# Token env-var names
# ---------------------------------------------------------------------------
_SANDBOX_TOKEN_VAR = "EDEN_AI_SANDBOX_API_TOKEN"
_PRODUCTION_TOKEN_VAR = "EDEN_AI_PRODUCTION_API_TOKEN"

# MDX source files whose snippets require a production (non-sandbox) API token.
# These use v2 admin/dashboard endpoints (cost management, token management)
# that are not supported by sandbox tokens.
_PRODUCTION_TOKEN_FILES = {
    "v3/how-to/cost-management/monitor-usage.mdx",
    "v3/how-to/user-management/manage-tokens.mdx",
    "v3/tutorials/multi-environment-tokens.mdx",
    "v3/tutorials/track-optimize-spending.mdx",
}


def _token_var_for(source_mdx: str) -> str:
    """Return the env-var name for the API token a given file's snippets need."""
    if source_mdx in _PRODUCTION_TOKEN_FILES:
        return _PRODUCTION_TOKEN_VAR
    return _SANDBOX_TOKEN_VAR


API_KEY_PATTERNS = [
    (
        re.compile(r'f"Bearer\s+(YOUR_API_KEY|YOUR_EDEN_AI_API_KEY)"'),
        "f\"Bearer {{os.environ['{token_var}']}}\"",
    ),
    (
        re.compile(r'"Bearer\s+(YOUR_API_KEY|YOUR_EDEN_AI_API_KEY)"'),
        "f\"Bearer {{os.environ['{token_var}']}}\"",
    ),
    (
        re.compile(r'"(YOUR_API_KEY|YOUR_EDEN_AI_API_KEY)"'),
        'os.environ["{token_var}"]',
    ),
    # os.getenv("EDEN_AI_API_KEY") or os.environ.get("EDEN_AI_API_KEY")
    (
        re.compile(r'os\.(?:getenv|environ\.get)\(\s*"EDEN_AI_API_KEY"\s*\)'),
        'os.environ["{token_var}"]',
    ),
]

# Matches bare API_KEY usage (not inside a string, not as part of a longer name)
_BARE_API_KEY_RE = re.compile(r"\bAPI_KEY\b")
# Matches lines that define API_KEY with a string literal (e.g. `API_KEY = "eyJhbG..."`)
_API_KEY_ASSIGNMENT_RE = re.compile(r"^\s*API_KEY\s*=", re.MULTILINE)
_API_KEY_STR_ASSIGNMENT_RE = re.compile(
    r'^(\s*)API_KEY\s*=\s*"[^"]*"', re.MULTILINE
)

# Default production base URL — replaced with env var in generated modules
_DEFAULT_BASE_URL = "https://staging-api.edenai.run"

# Placeholder file UUID used in documentation examples — replaced at runtime
# with a real file ID uploaded during test setup (see conftest.py).
_PLACEHOLDER_FILE_ID = "550e8400-e29b-41d4-a716-446655440000"

# Regex matching "https://api.edenai.run" inside a quoted string.
# Captures: (prefix_quote)(url)(rest_of_string_and_quote)
# Works for both plain strings and f-strings.
_BASE_URL_IN_PLAIN_STR_RE = re.compile(
    r"""(?<![f])("https://api\.edenai\.run)"""
)
_BASE_URL_IN_FSTR_RE = re.compile(
    r"""(f"[^"]*?)https://api\.edenai\.run"""
)


DOCS_ROOT = Path(__file__).resolve().parent.parent
GENERATED_DIR = Path(__file__).resolve().parent / "generated"


def extract_python_blocks(mdx_path: Path) -> list[dict]:
    """Extract all Python code blocks from an .mdx file.

    Returns a list of dicts with keys:
        - code: the raw code string
        - line: the 1-based line number where the block starts in the .mdx
    """
    content = mdx_path.read_text()
    blocks = []
    for match in CODE_BLOCK_RE.finditer(content):
        # Skip blocks preceded by {/* skip-test */} within the last 3 lines
        preceding = content[: match.start()]
        recent_lines = preceding.rsplit("\n", 3)[-3:]
        if any(_SKIP_COMMENT_RE.search(line) for line in recent_lines):
            continue
        code = match.group(1)
        # Calculate the line number of the code block start
        line = preceding.count("\n") + 2  # +2: fence line + first code line
        blocks.append({"code": code, "line": line})
    return blocks


def replace_api_keys(code: str, token_var: str = _SANDBOX_TOKEN_VAR) -> str:
    for pattern, replacement_template in API_KEY_PATTERNS:
        replacement = replacement_template.format(token_var=token_var)
        code = pattern.sub(replacement, code)
    # Replace API_KEY = "<any string>" with env-var lookup
    if _API_KEY_STR_ASSIGNMENT_RE.search(code):
        code = _API_KEY_STR_ASSIGNMENT_RE.sub(
            rf'\g<1>API_KEY = os.environ["{token_var}"]', code
        )
    # If code uses bare API_KEY variable but never defines it, prepend a definition
    elif _BARE_API_KEY_RE.search(code) and not _API_KEY_ASSIGNMENT_RE.search(code):
        code = f'API_KEY = os.environ["{token_var}"]\n' + code
    return code


def replace_placeholder_file_id(code: str) -> str:
    """Replace the placeholder file UUID with a runtime env-var lookup.

    The conftest.py fixture uploads a real file and sets _EDEN_TEST_FILE_ID.
    """
    if _PLACEHOLDER_FILE_ID not in code:
        return code
    return code.replace(
        f'"{_PLACEHOLDER_FILE_ID}"',
        '_EDEN_TEST_FILE_ID',
    )


def replace_base_url(code: str) -> str:
    """Replace hardcoded https://api.edenai.run with the _EDEN_BASE_URL variable.

    Handles both plain strings and f-strings:
      "https://api.edenai.run/v3/..."  -> f"{_EDEN_BASE_URL}/v3/..."
      f"...https://api.edenai.run..."  -> f"...{_EDEN_BASE_URL}..."
    """
    # First pass: plain strings (not already f-strings)
    code = _BASE_URL_IN_PLAIN_STR_RE.sub(r'f"{_EDEN_BASE_URL}', code)
    # Second pass: already f-strings
    code = _BASE_URL_IN_FSTR_RE.sub(r"\g<1>{_EDEN_BASE_URL}", code)
    return code


def build_module(blocks: list[dict], source_mdx: str) -> tuple[str, list[dict]]:
    """Build a Python module with one function per block.

    Returns:
        (module_code, block_functions) where block_functions is a list of dicts:
            - func_name: name of the generated function
            - block_indices: list with a single 1-based block number
            - lines: list with the line number from the .mdx
            - has_input: whether the block uses input()
            - needs_production_token: whether the block needs a production token
    """
    if not blocks:
        return "", []

    token_var = _token_var_for(source_mdx)
    needs_production_token = token_var == _PRODUCTION_TOKEN_VAR

    module_lines = [
        f"# Auto-generated from {source_mdx}",
        "# Do not edit — regenerated by snippet_extractor.py",
        "",
        "import os",
        "",
        f'_EDEN_BASE_URL = os.environ.get("EDEN_AI_BASE_URL", "{_DEFAULT_BASE_URL}")',
        f'_EDEN_TEST_FILE_ID = os.environ.get("_EDEN_TEST_FILE_ID", "{_PLACEHOLDER_FILE_ID}")',
    ]

    block_functions = []

    for i, block in enumerate(blocks):
        func_name = f"block_{i + 1}"
        code = replace_placeholder_file_id(replace_base_url(replace_api_keys(block["code"], token_var)))
        line_num = block["line"]
        has_input = "input(" in code

        module_lines.append("")
        module_lines.append("")
        module_lines.append(f"def {func_name}():")

        module_lines.append("")
        module_lines.append(f"    # {'=' * 70}")
        module_lines.append(
            f"    # Block {i + 1}/{len(blocks)} — {source_mdx}:{line_num}"
        )
        module_lines.append(f"    # {'=' * 70}")

        code_text = code.strip("\n")
        if code_text.strip():
            for line in code_text.split("\n"):
                if line.strip() == "":
                    module_lines.append("")
                else:
                    module_lines.append("    " + line)
        else:
            module_lines.append("    pass")

        block_functions.append({
            "func_name": func_name,
            "block_indices": [i + 1],
            "lines": [line_num],
            "has_input": has_input,
            "needs_production_token": needs_production_token,
        })

    # main() calls all functions in order for standalone execution
    module_lines.append("")
    module_lines.append("")
    module_lines.append("def main():")
    for bf in block_functions:
        module_lines.append(f"    {bf['func_name']}()")

    module_lines.append("")
    module_lines.append("")
    module_lines.append('if __name__ == "__main__":')
    module_lines.append("    main()")
    module_lines.append("")

    return "\n".join(module_lines), block_functions


def sanitize_filename(mdx_path: Path) -> str:
    """Convert an .mdx file path to a valid Python module name.

    e.g. v3/how-to/universal-ai/text-features.mdx -> v3_how_to_universal_ai_text_features
    """
    relative = mdx_path.relative_to(DOCS_ROOT)
    name = str(relative).replace("/", "_").replace("-", "_").replace(".mdx", "")
    # Ensure it's a valid Python identifier
    name = re.sub(r"[^a-zA-Z0-9_]", "_", name)
    if name[0].isdigit():
        name = "_" + name
    return name


def extract_all() -> list[dict]:
    """Extract snippets from all .mdx files and write generated modules.

    Returns a list of metadata dicts:
        - source_mdx: relative path to the .mdx file
        - module_name: Python module name (importable from tests.generated)
        - generated_path: absolute path to the generated .py file
        - snippet_count: number of Python code blocks found
        - has_input: whether any snippet uses input()
        - blocks: list of {code, line} dicts for individual syntax checking
        - block_functions: list of per-function metadata dicts
    """
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    init_file = GENERATED_DIR / "__init__.py"
    if not init_file.exists():
        init_file.write_text("")

    mdx_files = sorted(
        list(DOCS_ROOT.glob("v3/**/*.mdx")) + list(DOCS_ROOT.glob("*.mdx"))
    )
    results = []

    for mdx_path in mdx_files:
        blocks = extract_python_blocks(mdx_path)
        if not blocks:
            continue

        source_mdx = str(mdx_path.relative_to(DOCS_ROOT))
        module_name = sanitize_filename(mdx_path)
        module_code, block_functions = build_module(blocks, source_mdx)
        generated_path = GENERATED_DIR / f"{module_name}.py"

        generated_path.write_text(module_code)

        has_input = any(bf["has_input"] for bf in block_functions)

        results.append(
            {
                "source_mdx": source_mdx,
                "module_name": module_name,
                "generated_path": str(generated_path),
                "snippet_count": len(blocks),
                "has_input": has_input,
                "blocks": blocks,
                "block_functions": block_functions,
            }
        )

    return results


def extract_individual_blocks() -> list[dict]:
    """Extract individual Python code blocks for syntax testing.

    Returns a flat list of dicts:
        - source_mdx: relative path to the .mdx file
        - code: raw code string
        - line: starting line number in the .mdx file
        - block_index: 0-based index within the file
    """
    mdx_files = sorted(
        list(DOCS_ROOT.glob("v3/**/*.mdx")) + list(DOCS_ROOT.glob("*.mdx"))
    )
    results = []

    for mdx_path in mdx_files:
        blocks = extract_python_blocks(mdx_path)
        source_mdx = str(mdx_path.relative_to(DOCS_ROOT))

        for i, block in enumerate(blocks):
            results.append(
                {
                    "source_mdx": source_mdx,
                    "code": block["code"],
                    "line": block["line"],
                    "block_index": i,
                }
            )

    return results


if __name__ == "__main__":
    # Run standalone to extract and report
    results = extract_all()
    total_snippets = sum(r["snippet_count"] for r in results)
    print(f"Extracted {total_snippets} Python snippets from {len(results)} .mdx files")
    print(f"Generated {total_snippets} test functions (1 per block)")
    print()
    for r in results:
        flag = " [has input()]" if r["has_input"] else ""
        print(f"  {r['source_mdx']}: {r['snippet_count']} snippets{flag}")
