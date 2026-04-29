"""Pytest configuration and shared fixtures for the deepeval eval pipeline."""

from __future__ import annotations

import json
import os
from pathlib import Path

import httpx
import pytest

from context_loader import load_doc_context
from edenai_llm import DEFAULT_BASE_URL, DEFAULT_MODEL, EdenAILLM
from mintlify_client import ask_mintlify

EVALS_DIR = Path(__file__).resolve().parent
CACHE_DIR = EVALS_DIR / ".cache"
ANSWERS_CACHE = CACHE_DIR / "answers.json"

with open(EVALS_DIR / "dataset.json") as f:
    DATASET_ENTRIES: list[dict] = json.load(f)


# ---------------------------------------------------------------------------
# Pytest hooks
# ---------------------------------------------------------------------------


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--refresh-answers",
        action="store_true",
        default=False,
        help="Re-fetch all Mintlify Ask AI answers (ignoring cache).",
    )
    parser.addoption(
        "--category",
        action="store",
        default=None,
        choices=["llm", "expert-models", "integrations", "general", "cross-cutting"],
        help="Filter tests by category.",
    )
    parser.addoption(
        "--difficulty",
        action="store",
        default=None,
        choices=["basic", "intermediate", "advanced"],
        help="Filter tests by difficulty.",
    )


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    if "entry" in metafunc.fixturenames:
        entries = DATASET_ENTRIES
        for opt, key in [
            ("--category", "category"),
            ("--difficulty", "difficulty"),
        ]:
            val = metafunc.config.getoption(opt)
            if val:
                entries = [e for e in entries if e[key] == val]
        metafunc.parametrize("entry", entries, ids=lambda e: e["id"])


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def edenai_llm() -> EdenAILLM:
    api_key = os.environ["EDEN_AI_PRODUCTION_API_TOKEN"]
    base_url = os.getenv("EDEN_AI_BASE_URL", DEFAULT_BASE_URL) + "/v3"
    model = os.getenv("EVAL_JUDGE_MODEL", DEFAULT_MODEL)
    return EdenAILLM(api_key=api_key, base_url=base_url, model=model)


@pytest.fixture(scope="session")
def mintlify_cache(request: pytest.FixtureRequest) -> dict[str, dict]:
    """Fetch (or load cached) Mintlify Ask AI responses for every question.

    Each entry is ``{"answer": str, "retrieved_paths": list[str]}``.
    Cached to ``evals/.cache/answers.json``.  Use ``--refresh-answers``
    to force a re-fetch.
    """
    refresh = request.config.getoption("--refresh-answers")

    if not refresh and ANSWERS_CACHE.exists():
        with open(ANSWERS_CACHE) as f:
            cached = json.load(f)
        # Migrate old format: plain string values → dict with answer key
        if cached and isinstance(next(iter(cached.values())), str):
            cached = {
                qid: {"answer": text, "retrieved_paths": []}
                for qid, text in cached.items()
            }
        return cached

    api_key = os.getenv("MINTLIFY_API_KEY")
    if not api_key:
        pytest.skip("MINTLIFY_API_KEY not set and no cached answers available")

    cache: dict[str, dict] = {}
    with httpx.Client(timeout=60) as client:
        for entry in DATASET_ENTRIES:
            qid = entry["id"]
            resp = ask_mintlify(entry["question"], api_key, client=client)
            cache[qid] = {
                "answer": resp.answer,
                "retrieved_paths": resp.retrieved_paths,
            }

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with open(ANSWERS_CACHE, "w") as f:
        json.dump(cache, f, indent=2)

    return cache


@pytest.fixture
def actual_output(entry: dict, mintlify_cache: dict[str, dict]) -> str:
    """Get the Mintlify answer for the current entry, skip if empty."""
    answer = mintlify_cache[entry["id"]]["answer"]
    if not answer:
        pytest.skip(f"Mintlify returned empty answer for {entry['id']}")
    return answer


@pytest.fixture
def retrieved_paths(entry: dict, mintlify_cache: dict[str, dict]) -> list[str]:
    """Get the pages Mintlify retrieved for the current entry."""
    return mintlify_cache[entry["id"]].get("retrieved_paths", [])


@pytest.fixture(scope="session")
def doc_contexts() -> dict[str, list[str]]:
    """Load retrieval contexts from .mdx source docs."""
    contexts: dict[str, list[str]] = {}
    for entry in DATASET_ENTRIES:
        contexts[entry["id"]] = load_doc_context(entry["source_doc"])
    return contexts
