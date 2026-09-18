"""Extract Python code snippets from .mdx documentation files."""

import re
import textwrap
from pathlib import Path

from filelock import FileLock

# Both the indentation and the label are optional and free-form: a fence nested
# in a <Step> or <Accordion> is indented, and a <CodeGroup> tab reads
# "python OpenAI SDK (Multipart)". Insisting on column zero and a single label
# token silently dropped those blocks, so nothing tested them and nothing
# counted them as skipped either.
CODE_BLOCK_RE = re.compile(
    r"^[ \t]*```python(?:[ \t]+[^\n]*?)?[ \t]*\n(.*?)^\s*```",
    re.MULTILINE | re.DOTALL,
)

# Either marker may carry a reason: {/* skip-test: why this cannot run */}
_SKIP_COMMENT_RE = re.compile(r"\{/\*\s*skip-test\b[:\s]*(?P<reason>.*?)\s*\*/\}")

# A sample the sandbox cannot serve because it needs the model to answer for
# real, not with the sandbox's one canned completion. These spend credits every
# time they run, so they take the production token and only execute when the
# run opts in.
_PAID_COMMENT_RE = re.compile(r"\{/\*\s*paid-test\b[:\s]*(?P<reason>.*?)\s*\*/\}")

PAID_CALLS_ENV_VAR = "EDEN_AI_RUN_PAID_CALLS"

_SANDBOX_TOKEN_VAR = "EDEN_AI_SANDBOX_API_TOKEN"
_PRODUCTION_TOKEN_VAR = "EDEN_AI_PRODUCTION_API_TOKEN"
_MANAGEMENT_KEY_VAR = "EDEN_AI_MANAGEMENT_KEY"

# Pages that act on real account resources rather than on a model, so the
# sandbox token has nothing to act on. These cost nothing to run. Samples that
# need a real *model* answer are marked per block with {/* paid-test */}
# instead, since a page usually mixes the two.
_PRODUCTION_TOKEN_FILES = {
    "v3/how-to/cost-management/monitor-usage.mdx",
    "v3/how-to/user-management/manage-tokens.mdx",
    "v3/tutorials/multi-environment-tokens.mdx",
}


# Guides whose samples reach Eden AI through a third-party SDK that hardcodes
# the production endpoint. Those samples cannot honour EDEN_AI_BASE_URL, so a
# run pointed anywhere else reports them as skipped instead of failing on the
# 401 a staging token gets from production.
_PRODUCTION_BASE_URL_FILES = {
    "v3/integrations/haystack.mdx",
}

PRODUCTION_BASE_URL = "https://api.edenai.run"


def _token_var_for(source_mdx: str, paid: bool = False) -> str:
    if paid or source_mdx in _PRODUCTION_TOKEN_FILES:
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
    (
        re.compile(r'os\.(?:getenv|environ\.get)\(\s*"EDEN_AI_API_KEY"\s*\)'),
        'os.environ["{token_var}"]',
    ),
]

# Samples that call the Management API (/v3/manage/...) use this placeholder
# instead of YOUR_API_KEY. It is swapped for EDEN_AI_MANAGEMENT_KEY whatever
# file the block lives in, so a page can mix inference and management samples.
MANAGEMENT_KEY_PATTERNS = [
    (
        re.compile(r'f"Bearer\s+YOUR_MANAGEMENT_KEY"'),
        f"f\"Bearer {{os.environ['{_MANAGEMENT_KEY_VAR}']}}\"",
    ),
    (
        re.compile(r'"Bearer\s+YOUR_MANAGEMENT_KEY"'),
        f"f\"Bearer {{os.environ['{_MANAGEMENT_KEY_VAR}']}}\"",
    ),
    (
        re.compile(r'"YOUR_MANAGEMENT_KEY"'),
        f'os.environ["{_MANAGEMENT_KEY_VAR}"]',
    ),
]

# The sandbox page names its placeholder YOUR_SANDBOX_TOKEN rather than
# YOUR_API_KEY, because the point of the page is that this token is not the
# production one. It always resolves to the sandbox token, whatever the rest of
# the file uses.
SANDBOX_TOKEN_PATTERNS = [
    (
        re.compile(r'f"Bearer\s+YOUR_SANDBOX_TOKEN"'),
        f"f\"Bearer {{os.environ['{_SANDBOX_TOKEN_VAR}']}}\"",
    ),
    (
        re.compile(r'"Bearer\s+YOUR_SANDBOX_TOKEN"'),
        f"f\"Bearer {{os.environ['{_SANDBOX_TOKEN_VAR}']}}\"",
    ),
    (
        re.compile(r'"YOUR_SANDBOX_TOKEN"'),
        f'os.environ["{_SANDBOX_TOKEN_VAR}"]',
    ),
]

_BARE_API_KEY_RE = re.compile(r"\bAPI_KEY\b")
_API_KEY_ASSIGNMENT_RE = re.compile(r"^\s*API_KEY\s*=", re.MULTILINE)
_API_KEY_STR_ASSIGNMENT_RE = re.compile(r'^(\s*)API_KEY\s*=\s*"[^"]*"', re.MULTILINE)

DEFAULT_BASE_URL = "https://staging-api.edenai.run"
_PLACEHOLDER_FILE_ID = "550e8400-e29b-41d4-a716-446655440000"

_BASE_URL_IN_PLAIN_STR_RE = re.compile(r"""(?<![f])("https://api\.edenai\.run)""")
_BASE_URL_IN_FSTR_RE = re.compile(r"""(f"[^"]*?)https://api\.edenai\.run""")


DOCS_ROOT = Path(__file__).resolve().parent.parent
GENERATED_DIR = Path(__file__).resolve().parent / "generated"


def _first_marker(pattern: re.Pattern, lines: list[str]) -> re.Match | None:
    """Return the first match of a marker pattern across the given lines."""
    for line in lines:
        match = pattern.search(line)
        if match:
            return match
    return None


def extract_python_blocks(mdx_path: Path) -> list[dict]:
    """Extract all Python code blocks from an .mdx file."""
    content = mdx_path.read_text(encoding="utf-8")
    blocks = []
    for match in CODE_BLOCK_RE.finditer(content):
        preceding = content[: match.start()]
        recent_lines = preceding.rsplit("\n", 3)[-3:]
        skip = _first_marker(_SKIP_COMMENT_RE, recent_lines)
        paid = _first_marker(_PAID_COMMENT_RE, recent_lines)
        # A nested fence carries its own indentation, which is not part of the
        # sample.
        code = textwrap.dedent(match.group(1))
        line = preceding.count("\n") + 2
        blocks.append(
            {
                "code": code,
                "line": line,
                "skip": skip is not None,
                "skip_reason": skip.group("reason") if skip else "",
                "paid": paid is not None,
                "paid_reason": paid.group("reason") if paid else "",
            }
        )
    return blocks


def replace_api_keys(code: str, token_var: str = _SANDBOX_TOKEN_VAR) -> str:
    for pattern, replacement_template in API_KEY_PATTERNS:
        replacement = replacement_template.format(token_var=token_var)
        code = pattern.sub(replacement, code)
    if _API_KEY_STR_ASSIGNMENT_RE.search(code):
        code = _API_KEY_STR_ASSIGNMENT_RE.sub(
            rf'\g<1>API_KEY = os.environ["{token_var}"]', code
        )
    elif _BARE_API_KEY_RE.search(code) and not _API_KEY_ASSIGNMENT_RE.search(code):
        code = f'API_KEY = os.environ["{token_var}"]\n' + code
    return code


def replace_management_keys(code: str) -> str:
    for pattern, replacement in MANAGEMENT_KEY_PATTERNS:
        code = pattern.sub(replacement, code)
    return code


def replace_sandbox_tokens(code: str) -> str:
    for pattern, replacement in SANDBOX_TOKEN_PATTERNS:
        code = pattern.sub(replacement, code)
    return code


def replace_placeholder_file_id(code: str) -> str:
    """Replace the placeholder file UUID with an inline os.environ.get() call.

    The conftest.py fixture uploads a real file and sets _EDEN_TEST_FILE_ID.
    """
    if _PLACEHOLDER_FILE_ID not in code:
        return code
    return code.replace(
        f'"{_PLACEHOLDER_FILE_ID}"',
        f'os.environ.get("_EDEN_TEST_FILE_ID", "{_PLACEHOLDER_FILE_ID}")',
    )


def replace_base_url(code: str) -> str:
    """Replace hardcoded https://api.edenai.run with the _EDEN_BASE_URL variable."""
    code = _BASE_URL_IN_PLAIN_STR_RE.sub(r'f"{_EDEN_BASE_URL}', code)
    code = _BASE_URL_IN_FSTR_RE.sub(r"\g<1>{_EDEN_BASE_URL}", code)
    return code


def build_module(blocks: list[dict], source_mdx: str) -> tuple[str, list[dict]]:
    """Build a Python module with one function per block.

    Known limitation: each snippet is wrapped in a `def block_N():` function,
    so top-level class/def definitions inside a snippet become nested. This
    changes semantics for framework decorators, cross-file imports, etc.
    Snippets with such constructs should be marked with {/* skip-test */}.
    """
    if not blocks:
        return "", []

    needs_production_base_url = source_mdx in _PRODUCTION_BASE_URL_FILES

    module_lines = [
        f"# Auto-generated from {source_mdx}",
        "# Do not edit — regenerated by snippet_extractor.py",
        "",
        "import os",
        "",
        f'_EDEN_BASE_URL = os.environ.get("EDEN_AI_BASE_URL", "{DEFAULT_BASE_URL}")',
    ]

    block_functions = []

    for i, block in enumerate(blocks):
        func_name = f"block_{i + 1}"
        paid = block.get("paid", False)
        token_var = _token_var_for(source_mdx, paid)
        needs_production_token = token_var == _PRODUCTION_TOKEN_VAR
        code = replace_management_keys(block["code"])
        code = replace_sandbox_tokens(code)
        code = replace_api_keys(code, token_var)
        code = replace_base_url(code)
        code = replace_placeholder_file_id(code)
        line_num = block["line"]
        has_input = "input(" in code
        needs_management_key = _MANAGEMENT_KEY_VAR in code

        module_lines.append("")
        module_lines.append("")
        module_lines.append(f"def {func_name}():")

        code_text = code.strip("\n")
        for line in code_text.split("\n"):
            module_lines.append("    " + line)

        block_functions.append(
            {
                "func_name": func_name,
                "block_indices": [i + 1],
                "lines": [line_num],
                "has_input": has_input,
                "needs_production_token": needs_production_token,
                "needs_production_base_url": needs_production_base_url,
                "paid": paid,
                "paid_reason": block.get("paid_reason", ""),
                "needs_management_key": needs_management_key,
                "skip": block.get("skip", False),
                "skip_reason": block.get("skip_reason", ""),
            }
        )

    module_lines.append("")

    return "\n".join(module_lines), block_functions


def sanitize_filename(mdx_path: Path) -> str:
    """Convert an .mdx file path to a valid Python module name.

    e.g. v3/how-to/universal-ai/text-features.mdx -> v3_how_to_universal_ai_text_features
    """
    relative = mdx_path.relative_to(DOCS_ROOT)
    name = str(relative).replace("/", "_").replace("-", "_").replace(".mdx", "")
    name = re.sub(r"[^a-zA-Z0-9_]", "_", name)
    if name[0].isdigit():
        name = "_" + name
    return name


_EXTRACT_LOCK = GENERATED_DIR / ".extract.lock"


def extract_all() -> list[dict]:
    """Extract snippets from all .mdx files and write generated modules."""
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

        with FileLock(str(_EXTRACT_LOCK)):
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


if __name__ == "__main__":
    results = extract_all()
    total_snippets = sum(r["snippet_count"] for r in results)
    print(f"Extracted {total_snippets} Python snippets from {len(results)} .mdx files")
    print(f"Generated {total_snippets} test functions (1 per block)")
    print()
    for r in results:
        flag = " [has input()]" if r["has_input"] else ""
        print(f"  {r['source_mdx']}: {r['snippet_count']} snippets{flag}")
