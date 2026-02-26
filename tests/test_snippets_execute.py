"""Execution tests for documentation code snippets.

Imports the generated modules and calls each block function independently.
Requires EDEN_AI_API_KEY environment variable (sandbox token).
"""

import importlib
import os

import pytest

from tests.snippet_extractor import extract_all

# Skip the entire module if no API key is set
pytestmark = pytest.mark.skipif(
    not os.environ.get("EDEN_AI_API_KEY"),
    reason="EDEN_AI_API_KEY not set — skipping execution tests",
)

# Extract modules once at module level for parametrization
_modules = extract_all()

# Flatten to per-function test cases
_test_cases = []
for _mod in _modules:
    for _bf in _mod["block_functions"]:
        _test_cases.append(
            {
                "source_mdx": _mod["source_mdx"],
                "module_name": _mod["module_name"],
                "func_name": _bf["func_name"],
                "block_indices": _bf["block_indices"],
                "lines": _bf["lines"],
                "has_input": _bf["has_input"],
            }
        )


def _case_id(case: dict) -> str:
    """Generate a readable test ID: source_mdx::block[1,2,3]"""
    blocks_str = ",".join(str(b) for b in case["block_indices"])
    return f"{case['source_mdx']}::block[{blocks_str}]"


@pytest.mark.execute
@pytest.mark.parametrize(
    "test_case", _test_cases, ids=[_case_id(c) for c in _test_cases]
)
def test_snippet_executes(test_case, fixtures_dir, monkeypatch):
    """Import and execute a single block function from a generated module."""
    module_name = test_case["module_name"]
    func_name = test_case["func_name"]
    has_input = test_case["has_input"]

    # Change to fixtures directory so open("image.jpg", "rb") works
    monkeypatch.chdir(fixtures_dir)

    # Mock input() for interactive snippets
    if has_input:
        responses = iter(["test input", "quit"])
        monkeypatch.setattr("builtins.input", lambda prompt="": next(responses))

    # Import and run the specific block function
    full_module = f"tests.generated.{module_name}"
    module = importlib.import_module(full_module)
    # Reload to ensure fresh state (modules may have been imported by a previous test)
    module = importlib.reload(module)

    func = getattr(module, func_name)
    func()
