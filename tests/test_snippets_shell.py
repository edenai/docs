"""Execution tests for the shell snippets in the documentation.

A shell block is run rather than imported: the extractor writes each one to a
script under tests/generated/sh/ and this module runs it with bash, so what
gets tested is the command a reader would paste, quoting and all.

The scripts wrap the block in shims instead of rewriting it. curl exits 0 on a
4xx or 5xx unless told otherwise, so a retired endpoint would pass silently;
the shim adds --fail-with-body. The install commands resolve against their
index with --dry-run and leave the runner's environment alone.
"""

import os
import subprocess
from pathlib import Path

import pytest

from tests.snippet_extractor import (
    DEFAULT_BASE_URL,
    PAID_CALLS_ENV_VAR,
    extract_all_shell,
)

# Below the 300s pytest-timeout, so a slow endpoint gives us the command and
# its output rather than a bare "Timeout" from the plugin.
_TIMEOUT = 240

_blocks = extract_all_shell()


def _case_id(block: dict) -> str:
    return f"{block['source_mdx']}::shell[{block['block_index']}]"


def _paid_calls_enabled() -> bool:
    return os.environ.get(PAID_CALLS_ENV_VAR, "").strip().lower() in {
        "1",
        "true",
        "yes",
    }


@pytest.mark.execute
@pytest.mark.parametrize("block", _blocks, ids=[_case_id(b) for b in _blocks])
def test_shell_snippet_runs(block, fixtures_dir):
    """Run one documented shell command and fail on anything but success."""
    if not os.environ.get("EDEN_AI_SANDBOX_API_TOKEN"):
        pytest.skip("EDEN_AI_SANDBOX_API_TOKEN not set — skipping execution tests")

    if block["skip"]:
        reason = block["skip_reason"] or "no reason given"
        pytest.skip(f"marked with skip-test: {reason}")

    if block["paid"] and not _paid_calls_enabled():
        reason = block["paid_reason"] or "needs a real model answer"
        pytest.skip(f"spends credits ({reason}); set {PAID_CALLS_ENV_VAR}=1 to run")

    if block["needs_management_key"] and not os.environ.get("EDEN_AI_MANAGEMENT_KEY"):
        pytest.skip("EDEN_AI_MANAGEMENT_KEY not set")

    if block["needs_production_token"] and not os.environ.get(
        "EDEN_AI_PRODUCTION_API_TOKEN"
    ):
        pytest.skip("EDEN_AI_PRODUCTION_API_TOKEN not set")

    if block["needs_test_file"] and not os.environ.get("_EDEN_TEST_FILE_ID"):
        pytest.skip("no uploaded test file for this run")

    env = {
        **os.environ,
        "EDEN_AI_BASE_URL": os.environ.get("EDEN_AI_BASE_URL", DEFAULT_BASE_URL),
    }

    try:
        result = subprocess.run(
            ["bash", block["script_path"]],
            cwd=fixtures_dir,
            env=env,
            capture_output=True,
            text=True,
            timeout=_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        pytest.fail(
            f"{block['source_mdx']} line {block['line']} did not finish within "
            f"{_TIMEOUT}s:\n\n{_script_text(block)}"
        )

    if result.returncode != 0:
        pytest.fail(
            f"{block['source_mdx']} line {block['line']} exited "
            f"{result.returncode}\n\n"
            f"{_script_text(block)}\n"
            f"--- stdout ---\n{result.stdout}\n"
            f"--- stderr ---\n{result.stderr}"
        )


def _script_text(block: dict) -> str:
    """The script as it ran, so a failure can be reproduced by hand."""
    return Path(block["script_path"]).read_text(encoding="utf-8")
