"""Execution tests for the JavaScript and TypeScript snippets in the docs.

A JS block is run rather than imported: the extractor writes each one to a
script under tests/generated/js/ and this module hands it to node, so what
gets tested is the code a reader would paste.

node needs no build step for either language. A .mjs or .cjs runs as it is,
and a .mts or .cts has its type annotations stripped on load, which is why the
extension carries the language. Type *checking* is a separate matter and lives
in test_snippets_compile.py, since it needs no credentials.
"""

from pathlib import Path

import pytest

from tests.helpers.script_snippets import run_snippet_script, skip_unless_runnable
from tests.js_script import extract_all_js

_NODE_MODULES = Path(__file__).resolve().parent / "node_modules"

_blocks = extract_all_js()


def _case_id(block: dict) -> str:
    return f"{block['source_mdx']}::js[{block['block_index']}]"


@pytest.mark.execute
@pytest.mark.parametrize("block", _blocks, ids=[_case_id(b) for b in _blocks])
def test_js_snippet_runs(block, fixtures_dir):
    """Run one documented JS or TS snippet and fail on anything but success."""
    if block["needs_packages"] and not _NODE_MODULES.exists():
        pytest.skip("snippet packages not installed — run npm ci in tests/")

    skip_unless_runnable(block)
    run_snippet_script(["node", block["script_path"]], block, fixtures_dir)
