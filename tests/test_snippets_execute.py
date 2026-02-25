"""Execution tests for documentation code snippets.

Imports the generated modules and calls their main() function in-process.
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


def _module_id(mod: dict) -> str:
    """Generate a readable test ID from module metadata."""
    return mod["source_mdx"]


@pytest.mark.execute
@pytest.mark.parametrize("module_info", _modules, ids=[_module_id(m) for m in _modules])
def test_snippet_executes(module_info, fixtures_dir, monkeypatch):
    """Import and execute a generated snippet module."""
    module_name = module_info["module_name"]
    has_input = module_info["has_input"]

    # Change to fixtures directory so open("image.jpg", "rb") works
    monkeypatch.chdir(fixtures_dir)

    # Mock input() for interactive snippets
    if has_input:
        responses = iter(["test input", "quit"])
        monkeypatch.setattr("builtins.input", lambda prompt="": next(responses))

    # Import and run the module's main()
    full_module = f"tests.generated.{module_name}"
    module = importlib.import_module(full_module)
    # Reload to ensure fresh state (modules may have been imported by a previous test)
    module = importlib.reload(module)

    module.main()
