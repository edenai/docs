"""Execution tests for documentation code snippets."""

import importlib
import os

import pytest

from tests.snippet_extractor import extract_all

_modules = extract_all()

_test_cases = []
for _mod in _modules:
    for _bf in _mod["block_functions"]:
        _test_cases.append(
            {
                **_bf,
                "source_mdx": _mod["source_mdx"],
                "module_name": _mod["module_name"],
            }
        )


def _case_id(case: dict) -> str:
    blocks_str = ",".join(str(b) for b in case["block_indices"])
    return f"{case['source_mdx']}::block[{blocks_str}]"


@pytest.mark.execute
@pytest.mark.usefixtures("http_interceptor")
@pytest.mark.parametrize(
    "test_case", _test_cases, ids=[_case_id(c) for c in _test_cases]
)
def test_snippet_executes(test_case, fixtures_dir, monkeypatch):
    """Import and execute a single block function from a generated module."""
    module_name = test_case["module_name"]
    func_name = test_case["func_name"]
    has_input = test_case["has_input"]
    needs_production_token = test_case["needs_production_token"]

    if not os.environ.get("EDEN_AI_SANDBOX_API_TOKEN"):
        pytest.skip("EDEN_AI_SANDBOX_API_TOKEN not set — skipping execution tests")

    if test_case.get("skip"):
        pytest.skip("marked with {/* skip-test */}")

    if needs_production_token and not os.environ.get("EDEN_AI_PRODUCTION_API_TOKEN"):
        pytest.skip("EDEN_AI_PRODUCTION_API_TOKEN not set")

    monkeypatch.chdir(fixtures_dir)

    if has_input:
        responses = iter(["test input", "quit"])
        monkeypatch.setattr("builtins.input", lambda prompt="": next(responses))

    full_module = f"tests.generated.{module_name}"
    module = importlib.import_module(full_module)

    func = getattr(module, func_name)
    func()
