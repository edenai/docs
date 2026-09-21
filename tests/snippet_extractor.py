"""Extract code snippets from .mdx documentation files."""

import re
import textwrap
from pathlib import Path

from filelock import FileLock


def _fence_re(languages: str) -> re.Pattern:
    """A fenced code block regex for one or more languages.

    Both the indentation and the label are optional and free-form: a fence
    nested in a <Step> or <Accordion> is indented, and a <CodeGroup> tab reads
    "python OpenAI SDK (Multipart)". Insisting on column zero and a single
    label token silently dropped those blocks, so nothing tested them and
    nothing counted them as skipped either.
    """
    return re.compile(
        rf"^[ \t]*```(?P<lang>{languages})(?:[ \t]+[^\n]*?)?[ \t]*\n"
        r"(?P<code>.*?)^\s*```",
        re.MULTILINE | re.DOTALL,
    )


CODE_BLOCK_RE = _fence_re("python")
SHELL_BLOCK_RE = _fence_re("bash|shell|sh")

# javascript and typescript share a runner, and the fence language is what
# decides whether node is handed a .mjs or a .mts to strip types from.
JS_BLOCK_RE = _fence_re("javascript|typescript|js|ts")

# Configuration a reader pastes into another tool's config file. There is no
# program to run, so these are parsed and read rather than executed. nginx is
# deliberately absent: no parser reads it and it names no Eden AI models.
CONFIG_BLOCK_RE = _fence_re("json|yaml|yml|toml")

# Either marker may carry a reason: {/* skip-test: why this cannot run */}
_SKIP_COMMENT_RE = re.compile(r"\{/\*\s*skip-test\b[:\s]*(?P<reason>.*?)\s*\*/\}")

# A sample the sandbox cannot serve because it needs the model to answer for
# real, not with the sandbox's one canned completion. These spend credits every
# time they run, so they take the production token and only execute when the
# run opts in.
_PAID_COMMENT_RE = re.compile(r"\{/\*\s*paid-test\b[:\s]*(?P<reason>.*?)\s*\*/\}")

PAID_CALLS_ENV_VAR = "EDEN_AI_RUN_PAID_CALLS"

SANDBOX_TOKEN_VAR = "EDEN_AI_SANDBOX_API_TOKEN"
PRODUCTION_TOKEN_VAR = "EDEN_AI_PRODUCTION_API_TOKEN"
MANAGEMENT_KEY_VAR = "EDEN_AI_MANAGEMENT_KEY"

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


def token_var_for(source_mdx: str, paid: bool = False) -> str:
    if paid or source_mdx in _PRODUCTION_TOKEN_FILES:
        return PRODUCTION_TOKEN_VAR
    return SANDBOX_TOKEN_VAR


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
        f"f\"Bearer {{os.environ['{MANAGEMENT_KEY_VAR}']}}\"",
    ),
    (
        re.compile(r'"Bearer\s+YOUR_MANAGEMENT_KEY"'),
        f"f\"Bearer {{os.environ['{MANAGEMENT_KEY_VAR}']}}\"",
    ),
    (
        re.compile(r'"YOUR_MANAGEMENT_KEY"'),
        f'os.environ["{MANAGEMENT_KEY_VAR}"]',
    ),
]

# The sandbox page names its placeholder YOUR_SANDBOX_TOKEN rather than
# YOUR_API_KEY, because the point of the page is that this token is not the
# production one. It always resolves to the sandbox token, whatever the rest of
# the file uses.
SANDBOX_TOKEN_PATTERNS = [
    (
        re.compile(r'f"Bearer\s+YOUR_SANDBOX_TOKEN"'),
        f"f\"Bearer {{os.environ['{SANDBOX_TOKEN_VAR}']}}\"",
    ),
    (
        re.compile(r'"Bearer\s+YOUR_SANDBOX_TOKEN"'),
        f"f\"Bearer {{os.environ['{SANDBOX_TOKEN_VAR}']}}\"",
    ),
    (
        re.compile(r'"YOUR_SANDBOX_TOKEN"'),
        f'os.environ["{SANDBOX_TOKEN_VAR}"]',
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
SHELL_DIR = GENERATED_DIR / "sh"


def _first_marker(pattern: re.Pattern, lines: list[str]) -> re.Match | None:
    """Return the first match of a marker pattern across the given lines."""
    for line in lines:
        match = pattern.search(line)
        if match:
            return match
    return None


def _marker_lines(preceding: str) -> list[str]:
    """The lines a marker for the fence that follows may live on.

    The lines just above the fence, plus the lines just above the <CodeGroup>
    enclosing it. A group is marked as a whole and the marker sits above the
    group, so looking only above the fence finds it for the first tab and
    misses it for every other one.
    """
    lines = preceding.rsplit("\n", 3)[-3:]
    all_lines = preceding.split("\n")
    for i in range(len(all_lines) - 1, -1, -1):
        stripped = all_lines[i].strip()
        if stripped == "</CodeGroup>":
            break
        if stripped == "<CodeGroup>":
            lines += all_lines[max(0, i - 3) : i]
            break
    return lines


def _extract_blocks(mdx_path: Path, fence_re: re.Pattern) -> list[dict]:
    """Every fenced block matching one language, with its markers resolved."""
    content = mdx_path.read_text(encoding="utf-8")
    blocks = []
    for match in fence_re.finditer(content):
        preceding = content[: match.start()]
        recent_lines = _marker_lines(preceding)
        skip = _first_marker(_SKIP_COMMENT_RE, recent_lines)
        paid = _first_marker(_PAID_COMMENT_RE, recent_lines)
        # A nested fence carries its own indentation, which is not part of the
        # sample.
        code = textwrap.dedent(match.group("code"))
        line = preceding.count("\n") + 2
        blocks.append(
            {
                "code": code,
                "lang": match.group("lang"),
                "line": line,
                "skip": skip is not None,
                "skip_reason": skip.group("reason") if skip else "",
                "paid": paid is not None,
                "paid_reason": paid.group("reason") if paid else "",
            }
        )
    return blocks


# The placeholder vocabulary of the docs, shared by every runner. These match
# what a page writes; how a reference to the resolved value is rendered is the
# one part that differs per language ($VAR, ${process.env.VAR}, os.environ[...]),
# and each runner owns that itself.
MANAGEMENT_KEY_RE = re.compile(r"\bYOUR_MANAGEMENT_KEY\b")
SANDBOX_TOKEN_RE = re.compile(r"\bYOUR_SANDBOX_TOKEN\b")
FILE_PLACEHOLDER_RE = re.compile(r"\bYOUR_FILE_(?:UUID_OR_URL|ID)\b")
API_KEY_RE = re.compile(r"\bYOUR_(?:EDEN_AI_)?API_KEY\b")
BASE_URL_RE = re.compile(r"https://api\.edenai\.run")

BASE_URL_VAR = "EDEN_AI_BASE_URL"

# In a shell block a placeholder becomes a variable reference, which the runner
# exports before running the script. Every Authorization header in the docs is
# double quoted, which is what lets $VAR expand in place.
_SHELL_PLACEHOLDERS = [
    (MANAGEMENT_KEY_RE, MANAGEMENT_KEY_VAR),
    (SANDBOX_TOKEN_RE, SANDBOX_TOKEN_VAR),
]

# The run uploads one document and one image, because an image model rejects a
# PDF outright. Which one a sample wants is in the feature its model names.
# The key is quoted in JSON and bare in a JavaScript object literal, and the
# quotes differ too, so the match has to allow all of it: getting this wrong
# hands a sample the wrong fixture and the provider rejects it.
IMAGE_MODEL_RE = re.compile(r"""["']?model["']?\s*:\s*["']image/""")
TEST_FILE_VAR = "_EDEN_TEST_FILE_ID"
TEST_IMAGE_VAR = "_EDEN_TEST_IMAGE_ID"

# The shims are what make a shell block testable without touching the command
# the page shows. curl exits 0 on a 4xx or 5xx unless told otherwise, so a
# retired endpoint would pass silently; the install commands resolve against
# their index and leave this environment alone.
_SHELL_PREAMBLE = """\
#!/usr/bin/env bash
# Auto-generated from {source_mdx}
# Do not edit, regenerated by snippet_extractor.py
set -euo pipefail

curl() {{ command curl --fail-with-body --show-error "$@"; }}
pip() {{ command pip "$1" --dry-run "${{@:2}}"; }}
pip3() {{ command pip3 "$1" --dry-run "${{@:2}}"; }}
npm() {{ command npm "$1" --dry-run "${{@:2}}"; }}

"""


_UNESCAPED_QUOTE_RE = re.compile(r"(?<!\\)'")


def _shell_ref(code: str, start: int, var: str) -> str:
    """A reference to `var` that expands where the placeholder actually sits.

    Almost every curl body is -d '{...}', and the shell expands nothing inside
    single quotes, so a reference there has to close the quoting, expand, and
    reopen it. One sample writes an apostrophe as '\\'' , which is why only
    unescaped quotes count towards knowing which side we are on.
    """
    quotes = len(_UNESCAPED_QUOTE_RE.findall(code, 0, start))
    if quotes % 2:
        return f"'\"${var}\"'"
    return f"${var}"


def _sub_var(pattern: re.Pattern, var: str, code: str) -> str:
    """Replace a placeholder with a variable reference, quoting-aware.

    Safe to chain: the single-quoted form adds two quotes, so it leaves the
    parity that later passes depend on unchanged.
    """
    return pattern.sub(lambda m: _shell_ref(code, m.start(), var), code)


def shell_command(block: dict, source_mdx: str) -> str:
    """One shell block with its placeholders resolved, and nothing else."""
    code = block["code"]
    for pattern, var in _SHELL_PLACEHOLDERS:
        code = _sub_var(pattern, var, code)
    file_var = TEST_IMAGE_VAR if IMAGE_MODEL_RE.search(code) else TEST_FILE_VAR
    code = _sub_var(FILE_PLACEHOLDER_RE, file_var, code)
    token_var = token_var_for(source_mdx, block.get("paid", False))
    code = _sub_var(API_KEY_RE, token_var, code)
    return BASE_URL_RE.sub("$EDEN_AI_BASE_URL", code)


def build_shell_script(block: dict, source_mdx: str) -> str:
    """Wrap one shell block in the shims and resolve its placeholders."""
    command = shell_command(block, source_mdx).strip("\n")
    return _SHELL_PREAMBLE.format(source_mdx=source_mdx) + command + "\n"


def extract_python_blocks(mdx_path: Path) -> list[dict]:
    """Extract all Python code blocks from an .mdx file."""
    return _extract_blocks(mdx_path, CODE_BLOCK_RE)


def extract_shell_blocks(mdx_path: Path) -> list[dict]:
    """Extract all shell code blocks from an .mdx file."""
    return _extract_blocks(mdx_path, SHELL_BLOCK_RE)


def extract_js_blocks(mdx_path: Path) -> list[dict]:
    """Extract all JavaScript and TypeScript code blocks from an .mdx file."""
    return _extract_blocks(mdx_path, JS_BLOCK_RE)


def extract_config_blocks(mdx_path: Path) -> list[dict]:
    """Extract all JSON, YAML and TOML config blocks from an .mdx file."""
    return _extract_blocks(mdx_path, CONFIG_BLOCK_RE)


def replace_api_keys(code: str, token_var: str = SANDBOX_TOKEN_VAR) -> str:
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
        token_var = token_var_for(source_mdx, paid)
        needs_production_token = token_var == PRODUCTION_TOKEN_VAR
        code = replace_management_keys(block["code"])
        code = replace_sandbox_tokens(code)
        code = replace_api_keys(code, token_var)
        code = replace_base_url(code)
        code = replace_placeholder_file_id(code)
        line_num = block["line"]
        has_input = "input(" in code
        needs_management_key = MANAGEMENT_KEY_VAR in code

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


EXTRACT_LOCK = GENERATED_DIR / ".extract.lock"


def mdx_files() -> list[Path]:
    """Every published documentation page, in a stable order.

    The published tree is v3/ plus the pages at the repo root. A file under
    snippets/ is absent from docs.json and is not a page: it is included into
    one. Shared so the checks that walk the docs cannot disagree about what a
    page is.
    """
    return sorted([*DOCS_ROOT.glob("v3/**/*.mdx"), *DOCS_ROOT.glob("*.mdx")])


def extract_all() -> list[dict]:
    """Extract snippets from all .mdx files and write generated modules."""
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    init_file = GENERATED_DIR / "__init__.py"
    if not init_file.exists():
        init_file.write_text("")

    results = []

    # One acquisition for the whole pass rather than one per file. Every xdist
    # worker imports every suite module and so runs this, and they all contend
    # on the single lock file.
    with FileLock(str(EXTRACT_LOCK)):
        for mdx_path in mdx_files():
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


# What a shell block has to be for the suite to run it. Many pages drive
# somebody else's software rather than documenting an Eden AI call: they start
# containers, clone repositories, reset an admin password. Those are never
# turned into scripts, because a test run must not do any of it.
_EDEN_HOST_RE = re.compile(r"\$EDEN_AI_BASE_URL|https://api\.eu\.edenai\.run")
_LOCAL_HOST_RE = re.compile(r"\blocalhost\b|\b127\.0\.0\.1\b")
_CURL_RE = re.compile(r"(?<![\w-])curl\b")
_SUPPORTED_INSTALL_RE = re.compile(r"^(?:pip3?|npm)\s+(?:install|add)\b")

# A backstop. What keeps `docker run` out today is the curl requirement below,
# since naming the Eden AI URL is not the same as calling it: an open-webui
# sample passes it to docker as an environment variable. This catches the block
# that does both, which no page has yet and one may acquire.
_STATEFUL_COMMAND_RE = re.compile(
    r"^\s*(?:sudo|docker|git|systemctl|kill|chmod|chown|npm\s+run)\b",
    re.MULTILINE,
)


def _is_testable_shell(command: str) -> bool:
    """Whether a shell block is one of the two kinds this suite knows how to run.

    Either it calls Eden AI with curl, or it is a plain install whose only
    effect under the dry-run shim is to resolve a package. An install straight
    from a git repository is neither: resolving it clones the repository and
    runs its setup.py.
    """
    lines = [
        line.strip()
        for line in command.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    if not lines or _STATEFUL_COMMAND_RE.search(command):
        return False

    if _EDEN_HOST_RE.search(command) and _CURL_RE.search(command):
        return not _LOCAL_HOST_RE.search(command)

    return all(_SUPPORTED_INSTALL_RE.match(line) for line in lines) and (
        "git+" not in command
    )


def extract_all_shell() -> list[dict]:
    """Extract shell snippets from all .mdx files and write one script each.

    A shell block gets a script rather than a function in a shared module: it
    is run, not imported, and each one has to stand alone the way a reader
    pasting it into a terminal would.
    """
    SHELL_DIR.mkdir(parents=True, exist_ok=True)
    results = []

    # One acquisition for the whole pass rather than one per file. Every xdist
    # worker imports every suite module and so runs this, and they all contend
    # on the single lock file.
    with FileLock(str(EXTRACT_LOCK)):
        for mdx_path in mdx_files():
            blocks = extract_shell_blocks(mdx_path)
            if not blocks:
                continue

            source_mdx = str(mdx_path.relative_to(DOCS_ROOT))
            stem = sanitize_filename(mdx_path)

            for i, block in enumerate(blocks):
                if not _is_testable_shell(shell_command(block, source_mdx)):
                    continue
                script = build_shell_script(block, source_mdx)
                script_path = SHELL_DIR / f"{stem}__block_{i + 1}.sh"

                script_path.write_text(script)

                results.append(
                    {
                        "source_mdx": source_mdx,
                        "block_index": i + 1,
                        "line": block["line"],
                        "script_path": str(script_path),
                        "skip": block.get("skip", False),
                        "skip_reason": block.get("skip_reason", ""),
                        "paid": block.get("paid", False),
                        "paid_reason": block.get("paid_reason", ""),
                        "needs_management_key": f"${MANAGEMENT_KEY_VAR}" in script,
                        "needs_production_token": f"${PRODUCTION_TOKEN_VAR}" in script,
                        "needs_test_file": TEST_FILE_VAR in script
                        or TEST_IMAGE_VAR in script,
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
