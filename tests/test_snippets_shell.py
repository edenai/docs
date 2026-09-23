"""Execution tests for the shell snippets in the documentation.

A shell block is run rather than imported: the extractor writes each one to a
script under tests/generated/sh/ and this module runs it with bash, so what
gets tested is the command a reader would paste, quoting and all.

The scripts wrap the block in shims instead of rewriting it. curl exits 0 on a
4xx or 5xx unless told otherwise, so a retired endpoint would pass silently;
the shim adds --fail-with-body. The install commands resolve against their
index with --dry-run and leave the runner's environment alone.
"""

import pytest

from tests.helpers.script_snippets import run_snippet_script, skip_unless_runnable
from tests.snippet_extractor import extract_all_shell

_blocks = extract_all_shell()


def _case_id(block: dict) -> str:
    return f"{block['source_mdx']}::shell[{block['block_index']}]"


@pytest.mark.execute
@pytest.mark.parametrize("block", _blocks, ids=[_case_id(b) for b in _blocks])
def test_shell_snippet_runs(block, fixtures_dir):
    """Run one documented shell command and fail on anything but success."""
    skip_unless_runnable(block)
    run_snippet_script(["bash", block["script_path"]], block, fixtures_dir)
