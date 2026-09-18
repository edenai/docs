"""Syntax checks for every extracted snippet, including the ones that never run.

The execution suite runs a snippet only when nothing holds it back, so a block
marked skip-test or paid-test is never parsed at all and a syntax error in it
reaches the published docs unnoticed. These tests parse every extracted
snippet, cost nothing and need no credentials, so they run on every pull
request and cover the blocks the execution suite cannot.

This is a weaker check than executing the snippet. It catches the docs bugs
that are pure syntax (a dropped colon, an unclosed quote, the indentation
mistakes that MDX code fences invite), not a wrong endpoint or a renamed
response field.
"""

import re
import subprocess
from pathlib import Path

import pytest

from tests.js_script import extract_all_js
from tests.snippet_extractor import extract_all, extract_all_shell

_modules = extract_all()
_shell_blocks = extract_all_shell()
_js_blocks = extract_all_js()

_TESTS_DIR = Path(__file__).resolve().parent
_TSC = _TESTS_DIR / "node_modules" / ".bin" / "tsc"

# tsc reports one diagnostic per line: path(line,col): error TS1234: message
_TSC_DIAGNOSTIC_RE = re.compile(r"^(?P<file>[^(]+)\(\d+,\d+\):")


@pytest.mark.parametrize("module", _modules, ids=[m["source_mdx"] for m in _modules])
def test_snippet_module_compiles(module):
    """Every extracted snippet on the page is valid Python."""
    source = Path(module["generated_path"]).read_text(encoding="utf-8")
    try:
        compile(source, module["generated_path"], "exec")
    except SyntaxError as exc:
        pytest.fail(
            f"{module['source_mdx']} produced a snippet that is not valid "
            f"Python: {exc.msg} (generated line {exc.lineno})"
        )


@pytest.mark.parametrize(
    "block",
    _shell_blocks,
    ids=[f"{b['source_mdx']}::shell[{b['block_index']}]" for b in _shell_blocks],
)
def test_shell_snippet_parses(block):
    """Every extracted shell snippet is valid bash.

    `bash -n` reads the script and never runs it, so this holds for the blocks
    the execution suite holds back as well.
    """
    result = subprocess.run(
        ["bash", "-n", block["script_path"]],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        pytest.fail(
            f"{block['source_mdx']} line {block['line']} is not valid bash: "
            f"{result.stderr.strip()}"
        )


_plain_js_blocks = [
    b for b in _js_blocks if b["script_path"].endswith((".mjs", ".cjs"))
]


@pytest.mark.parametrize(
    "block",
    _plain_js_blocks,
    ids=[f"{b['source_mdx']}::js[{b['block_index']}]" for b in _plain_js_blocks],
)
def test_js_snippet_parses(block):
    """Every extracted JavaScript snippet is something node can read.

    `node --check` parses the file and never runs it, so this holds for the
    blocks the execution suite holds back as well. TypeScript is left to tsc
    below: --check falls back to parsing a .mts as CommonJS when the file has
    no import of its own, and then reports a type annotation as a syntax error
    in a file node runs quite happily.
    """
    result = subprocess.run(
        ["node", "--check", block["script_path"]],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        pytest.fail(
            f"{block['source_mdx']} line {block['line']} is not valid "
            f"{block['lang']}: {result.stderr.strip()}"
        )


@pytest.fixture(scope="session")
def tsc_diagnostics() -> dict[str, list[str]]:
    """Everything tsc objects to, once, grouped by the file it objects to.

    tsc takes the whole project at once, so it is run once and each block then
    asserts on its own file, which keeps a failure pointing at a single page
    rather than reporting every page together.
    """
    if not _TSC.exists():
        pytest.skip("tsc not installed — run npm ci in tests/")

    result = subprocess.run(
        [str(_TSC), "--noEmit", "-p", str(_TESTS_DIR / "tsconfig.json")],
        capture_output=True,
        text=True,
        timeout=300,
        cwd=_TESTS_DIR,
    )

    diagnostics: dict[str, list[str]] = {}
    for line in (result.stdout + result.stderr).splitlines():
        match = _TSC_DIAGNOSTIC_RE.match(line.strip())
        if match:
            name = Path(match.group("file")).name
            diagnostics.setdefault(name, []).append(line.strip())
    return diagnostics


_ts_blocks = [b for b in _js_blocks if b["script_path"].endswith((".mts", ".cts"))]


@pytest.mark.parametrize(
    "block",
    _ts_blocks,
    ids=[f"{b['source_mdx']}::ts[{b['block_index']}]" for b in _ts_blocks],
)
def test_ts_snippet_typechecks(block, tsc_diagnostics):
    """Every TypeScript snippet compiles against the SDK typings it imports.

    node strips the annotations rather than checking them, so a renamed option
    or a field the SDK no longer returns runs without complaint. A reader
    pasting the block into their own project sees the error we would not.

    This is also where a TypeScript block is checked for syntax at all, and
    where erasableSyntaxOnly rejects the TypeScript node cannot strip.
    """
    if not block["runnable"]:
        # Type-checking resolves the imports, so a block naming a package the
        # runner does not install cannot be checked here either. It is reported
        # rather than dropped, for the same reason the execution suite reports
        # it: the page is only part covered and that should be visible.
        pytest.skip(f"cannot be type-checked: {block['skip_reason']}")

    problems = tsc_diagnostics.get(Path(block["script_path"]).name, [])
    if problems:
        pytest.fail(
            f"{block['source_mdx']} line {block['line']} does not type-check:\n"
            + "\n".join(problems)
        )
