"""Shared behaviour for the snippet suites that run a script per block.

The shell and JS runners differ in one line, the command they hand the block
to. Everything around it, which credential or marker holds a block back and
what a failure has to print to be reproducible, is policy about the docs rather
than anything to do with the language, and it has to be the same for both: a
paid-test block must not run on a pull request whichever fence it came from.

Keeping it here is what makes that true by construction. The Python suite
imports its blocks rather than spawning them, so it does not use this.
"""

import os
import subprocess
from pathlib import Path

import pytest

from tests.helpers.env import env_flag
from tests.snippet_extractor import (
    DEFAULT_BASE_URL,
    MANAGEMENT_KEY_VAR,
    PAID_CALLS_ENV_VAR,
    PRODUCTION_TOKEN_VAR,
    SANDBOX_TOKEN_VAR,
)

# Below the 300s pytest-timeout, so a slow endpoint gives us the script and its
# output rather than a bare "Timeout" from the plugin.
TIMEOUT = 240


def paid_calls_enabled() -> bool:
    """Whether this run may spend credits on samples the sandbox cannot serve.

    Off by default, so neither a docs PR nor a local run bills the account. The
    weekly run turns it on, which is where these samples get their coverage.
    """
    return env_flag(PAID_CALLS_ENV_VAR)


def skip_unless_runnable(block: dict) -> None:
    """Hold the block back, with a reason, unless this run can honour it.

    Ordered cheapest first, and by how much the reader can do about it: a
    marker in the docs is an authoring decision, a missing credential is a
    property of the run.
    """
    if not os.environ.get(SANDBOX_TOKEN_VAR):
        pytest.skip(f"{SANDBOX_TOKEN_VAR} not set — skipping execution tests")

    if block["skip"]:
        reason = block["skip_reason"] or "no reason given"
        pytest.skip(f"marked with skip-test: {reason}")

    if block["paid"] and not paid_calls_enabled():
        reason = block["paid_reason"] or "needs a real model answer"
        pytest.skip(f"spends credits ({reason}); set {PAID_CALLS_ENV_VAR}=1 to run")

    if block["needs_management_key"] and not os.environ.get(MANAGEMENT_KEY_VAR):
        pytest.skip(f"{MANAGEMENT_KEY_VAR} not set")

    if block["needs_production_token"] and not os.environ.get(PRODUCTION_TOKEN_VAR):
        pytest.skip(f"{PRODUCTION_TOKEN_VAR} not set")

    if block["needs_test_file"] and not os.environ.get("_EDEN_TEST_FILE_ID"):
        pytest.skip("no uploaded test file for this run")


def run_snippet_script(argv: list[str], block: dict, cwd: Path) -> None:
    """Run one generated script and fail on anything but success.

    A failure prints the script as it ran, not as the page wrote it, because
    the placeholders are resolved by then and pasting it back into a terminal
    is how anybody works out what the API actually objected to.
    """
    env = {
        **os.environ,
        "EDEN_AI_BASE_URL": os.environ.get("EDEN_AI_BASE_URL", DEFAULT_BASE_URL),
    }

    where = f"{block['source_mdx']} line {block['line']}"

    try:
        result = subprocess.run(
            argv,
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            timeout=TIMEOUT,
            # A sample that prompts for input reads EOF and exits rather than
            # holding the whole run open until the timeout.
            stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired:
        pytest.fail(f"{where} did not finish within {TIMEOUT}s:\n\n{_text(block)}")

    if result.returncode != 0:
        pytest.fail(
            f"{where} exited {result.returncode}\n\n"
            f"{_text(block)}\n"
            f"--- stdout ---\n{result.stdout}\n"
            f"--- stderr ---\n{result.stderr}"
        )


def _text(block: dict) -> str:
    return Path(block["script_path"]).read_text(encoding="utf-8")
