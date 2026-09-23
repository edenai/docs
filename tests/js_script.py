"""Turn one JavaScript or TypeScript documentation block into a runnable script.

A JS block is run rather than imported, the way a shell block is: each one is
written to its own file under tests/generated/js/ and handed to node, so what
gets tested is the code a reader would paste rather than a translation of it.

Two things make that work. node resolves a placeholder through process.env,
which a plain quote does not interpolate, so the quote around the placeholder
becomes a backtick and the placeholder becomes ${...}. And fetch resolves
happily on a 4xx, so a block that calls it gets the same treatment curl gets
from --fail-with-body: the sample is left alone and what it calls is wrapped.
"""

import json
import re
from pathlib import Path

from filelock import FileLock

from tests.snippet_extractor import (
    API_KEY_RE,
    BASE_URL_RE,
    BASE_URL_VAR,
    DOCS_ROOT,
    EXTRACT_LOCK,
    FILE_PLACEHOLDER_RE,
    GENERATED_DIR,
    IMAGE_MODEL_RE,
    MANAGEMENT_KEY_RE,
    MANAGEMENT_KEY_VAR,
    PRODUCTION_TOKEN_VAR,
    SANDBOX_TOKEN_RE,
    SANDBOX_TOKEN_VAR,
    TEST_FILE_VAR,
    TEST_IMAGE_VAR,
    extract_js_blocks,
    mdx_files,
    sanitize_filename,
    token_var_for,
)

JS_DIR = GENERATED_DIR / "js"

# The SDK pages skip the placeholder and read the key out of the environment.
# That is already an expression rather than a fragment of a string, so it is
# substituted as it stands and never goes through the quoting rules below:
# inside `Bearer ${process.env.EDEN_AI_API_KEY}` those would nest a second
# ${...} in the first and produce something that does not parse.
ENV_KEY_RE = re.compile(r"\bprocess\.env\.EDEN_AI_API_KEY\b")


# --- placeholders --------------------------------------------------------


def _placeholder_rules(code: str, token_var: str) -> list[tuple[re.Pattern, str]]:
    """Every placeholder a block can carry, paired with its variable.

    Ordered so the specific keys are consumed before the general one, matching
    how the Python and shell rewrites read the same pages.
    """
    file_var = TEST_IMAGE_VAR if IMAGE_MODEL_RE.search(code) else TEST_FILE_VAR
    return [
        (MANAGEMENT_KEY_RE, MANAGEMENT_KEY_VAR),
        (SANDBOX_TOKEN_RE, SANDBOX_TOKEN_VAR),
        (FILE_PLACEHOLDER_RE, file_var),
        (API_KEY_RE, token_var),
        (BASE_URL_RE, BASE_URL_VAR),
    ]


# One JavaScript string literal. Templates come first so that a quote living
# inside one is never mistaken for a literal of its own, and neither plain
# form crosses a newline, because in JavaScript neither may.
_STRING_RE = re.compile(
    r"`(?:\\.|[^\\`])*`" r"|'(?:\\.|[^\\'\n])*'" r'|"(?:\\.|[^\\"\n])*"',
    re.DOTALL,
)


def js_source(block: dict, source_mdx: str) -> str:
    """One block with its placeholders resolved, and nothing else changed.

    A placeholder inside 'a plain quote' cannot interpolate, so the literal
    holding it becomes a template literal and the placeholder becomes ${...}.
    Working literal by literal rather than placeholder by placeholder is what
    makes the quotes easy to get right: the match already knows where the
    string ends, so nothing has to count quotes to find out.

    A placeholder outside every literal is already an expression and is
    substituted as it stands.
    """
    token_var = token_var_for(source_mdx, block.get("paid", False))
    rules = _placeholder_rules(block["code"], token_var)
    code = ENV_KEY_RE.sub(f"process.env.{token_var}", block["code"])

    def resolve(text: str, template: str) -> str:
        for pattern, var in rules:
            text = pattern.sub(template.format(var=var), text)
        return text

    def to_template(match: re.Match) -> str:
        literal = match.group(0)
        if not any(pattern.search(literal) for pattern, _ in rules):
            return literal
        body = literal[1:-1]
        if literal[0] != "`":
            # Now that it is a template literal, what it says has to survive
            # the change: a backtick or a ${ in the text would become syntax.
            body = body.replace("`", "\\`").replace("${", "\\${")
        return "`" + resolve(body, "${{process.env.{var}}}") + "`"

    return resolve(_STRING_RE.sub(to_template, code), "process.env.{var}")


# --- the script around it ------------------------------------------------

# fetch resolves on a 4xx or 5xx, so a sample that only prints the body would
# pass against a retired endpoint. The sample is never rewritten; what it calls
# is. The SDK blocks raise on their own, so they are left with the real fetch.
_FETCH_SHIM = """\
{
  const _fetch = globalThis.fetch;
  globalThis.fetch = async (input, init) => {
    const response = await _fetch(input, init);
    if (!response.ok) {
      const body = await response.clone().text();
      throw new Error(
        "HTTP " + response.status + " " + response.statusText + ": " + body,
      );
    }
    return response;
  };
}
"""

_BARE_FETCH_RE = re.compile(r"(?<![\w.$])fetch\s*\(")
_REQUIRE_RE = re.compile(r"""\brequire\(\s*['"]([^'"]+)['"]\s*\)""")
_IMPORT_RE = re.compile(
    r"""(?:^|\n)\s*import\s+(?:[^'"\n]*?\bfrom\s+)?['"]([^'"]+)['"]"""
)


def script_suffix(block: dict) -> str:
    """The extension node needs to read this block the way the page means it.

    CommonJS has no top-level await and almost every sample here uses one, so
    ESM is the default and only an explicit require() opts out. The language
    decides the rest: node strips the types, but only from a .mts or a .cts.
    """
    code = block["code"]
    commonjs = bool(_REQUIRE_RE.search(code)) and not _IMPORT_RE.search(code)
    typescript = block.get("lang", "javascript") in {"typescript", "ts"}
    if typescript:
        return ".cts" if commonjs else ".mts"
    return ".cjs" if commonjs else ".mjs"


def build_js_script(block: dict, source_mdx: str) -> str:
    """One block, its placeholders resolved and its fetch made to fail loudly."""
    header = (
        f"// Auto-generated from {source_mdx}\n"
        "// Do not edit, regenerated by js_script.py\n"
    )
    source = js_source(block, source_mdx).strip("\n")
    shim = _FETCH_SHIM if _BARE_FETCH_RE.search(block["code"]) else ""
    return f"{header}{shim}\n{source}\n"


# --- which blocks the suite is willing to run ----------------------------

PACKAGE_JSON = Path(__file__).resolve().parent / "package.json"

# tsc and its typings are how the snippets are checked, not something a snippet
# imports, so they are the one part of package.json that does not mean "a block
# importing this can run".
_TOOLING_PACKAGES = frozenset({"typescript", "@types/node"})


def _installed_packages() -> frozenset[str]:
    """What a block is allowed to import, read from the manifest that installs it.

    Kept in step with package.json by derivation rather than by hand. A copy
    would go stale silently and in the worst direction: adding a package for a
    new sample and forgetting the copy would leave every block importing it
    reported as unrunnable, which reads like a broken doc.
    """
    manifest = json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))
    return frozenset(manifest.get("devDependencies", {})) - _TOOLING_PACKAGES


INSTALLED_PACKAGES = _installed_packages()

# Only what the samples actually import, plus the near neighbours of those.
# Deliberately not node's whole builtin list: child_process and the networking
# modules would let a future sample run arbitrary software on the runner, which
# is the thing the shell rules go out of their way to prevent. A block that
# needs one of them is reported as unrunnable, which is a decision somebody can
# then make on purpose.
_NODE_BUILTINS = frozenset(
    {
        "assert",
        "buffer",
        "console",
        "crypto",
        "events",
        "fs",
        "fs/promises",
        "os",
        "path",
        "readline",
        "readline/promises",
        "stream",
        "string_decoder",
        "timers",
        "url",
        "util",
        "zlib",
    }
)


def _package_of(specifier: str) -> str:
    """The installable package a module specifier names.

    'openai/resources/chat/completions' is the openai package, and
    '@langchain/core/messages' is @langchain/core: a scoped name keeps two
    segments, a plain one keeps a single segment.
    """
    name = specifier.removeprefix("node:")
    parts = name.split("/")
    if name.startswith("@"):
        return "/".join(parts[:2])
    return parts[0]


def _imported_packages(code: str) -> set[str]:
    specifiers = _IMPORT_RE.findall(code) + _REQUIRE_RE.findall(code)
    return {_package_of(s) for s in specifiers if not s.startswith(".")}


def unrunnable_reason(code: str) -> str:
    """Why node cannot run this block, or "" if it can.

    A reason rather than a yes or no, because the suite reports the block as
    skipped and says why. Dropping it instead would make the count of what the
    docs contain disagree with the count of what the suite looked at, and the
    difference would be invisible: a React component and an Express receiver
    would simply cease to exist as far as any output was concerned.
    """
    if not code.strip():
        return "the block is empty"
    missing = sorted(_imported_packages(code) - _NODE_BUILTINS - INSTALLED_PACKAGES)
    if missing:
        return f"imports {', '.join(missing)}, which the runner does not install"
    return ""


def extract_all_js() -> list[dict]:
    """Extract JS and TS snippets from all .mdx files and write one script each."""
    JS_DIR.mkdir(parents=True, exist_ok=True)
    results = []

    # One acquisition for the whole pass rather than one per file. Every xdist
    # worker imports every suite module and so runs this, and the lock is a
    # single file shared by all of them.
    with FileLock(str(EXTRACT_LOCK)):
        for mdx_path in mdx_files():
            blocks = extract_js_blocks(mdx_path)
            if not blocks:
                continue

            source_mdx = str(mdx_path.relative_to(DOCS_ROOT))
            stem = sanitize_filename(mdx_path)

            for i, block in enumerate(blocks):
                script = build_js_script(block, source_mdx)
                script_path = JS_DIR / f"{stem}__block_{i + 1}{script_suffix(block)}"
                script_path.write_text(script, encoding="utf-8")

                unrunnable = unrunnable_reason(block["code"])
                results.append(
                    {
                        "source_mdx": source_mdx,
                        "block_index": i + 1,
                        "line": block["line"],
                        "lang": block["lang"],
                        "script_path": str(script_path),
                        "skip": block.get("skip", False) or bool(unrunnable),
                        "skip_reason": block.get("skip_reason", "") or unrunnable,
                        "paid": block.get("paid", False),
                        "paid_reason": block.get("paid_reason", ""),
                        "runnable": not unrunnable,
                        "needs_packages": bool(
                            _imported_packages(block["code"]) - _NODE_BUILTINS
                        ),
                        "needs_management_key": MANAGEMENT_KEY_VAR in script,
                        "needs_production_token": PRODUCTION_TOKEN_VAR in script,
                        "needs_test_file": TEST_FILE_VAR in script
                        or TEST_IMAGE_VAR in script,
                    }
                )

    return results
