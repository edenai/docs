"""Syntax checks for every extracted snippet, including the ones that never run.

The execution suite imports a generated module only when at least one of its
blocks actually executes, so a page whose blocks are all held back (skip-test,
paid-test, quota-test) is never compiled and a syntax error in it reaches the
published docs unnoticed. These tests compile every generated module, cost
nothing and need no credentials, so they run on every pull request and cover
the blocks the execution suite cannot.

This is a weaker check than executing the snippet. It catches the docs bugs
that are pure Python (a dropped colon, an unclosed bracket, the indentation
mistakes that MDX code fences invite), not a wrong endpoint or a renamed
response field.
"""

from pathlib import Path

import pytest

from tests.snippet_extractor import extract_all

_modules = extract_all()


@pytest.mark.parametrize(
    "module", _modules, ids=[m["source_mdx"] for m in _modules]
)
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
