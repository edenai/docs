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

import subprocess
from pathlib import Path

import pytest

from tests.snippet_extractor import extract_all, extract_all_shell

_modules = extract_all()
_shell_blocks = extract_all_shell()


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
