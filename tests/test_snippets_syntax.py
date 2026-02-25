"""Syntax validation tests for documentation code snippets.

Runs ast.parse() on each individual Python code block extracted from .mdx files.
Does NOT require an API key — pure static analysis.
"""

import ast

import pytest

from tests.snippet_extractor import extract_individual_blocks

# Extract blocks once at module level for parametrization
_blocks = extract_individual_blocks()


def _block_id(block: dict) -> str:
    """Generate a readable test ID from block metadata."""
    return f"{block['source_mdx']}:L{block['line']}[{block['block_index']}]"


@pytest.mark.syntax
@pytest.mark.parametrize("block", _blocks, ids=[_block_id(b) for b in _blocks])
def test_snippet_syntax(block):
    """Verify that each Python code block is syntactically valid."""
    code = block["code"]
    source_mdx = block["source_mdx"]
    line = block["line"]

    try:
        ast.parse(code)
    except SyntaxError as e:
        pytest.fail(
            f"Syntax error in {source_mdx} (line {line + (e.lineno or 1) - 1}):\n"
            f"  {e.msg}\n"
            f"  Block starts at line {line} in the .mdx file"
        )
