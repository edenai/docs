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

with open(EVALS_DIR / "dataset.json") as _f:
    DATASET_ENTRIES: list[dict] = json.load(_f)


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


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    if "entry" in metafunc.fixturenames:
        metafunc.parametrize("entry", DATASET_ENTRIES, ids=lambda e: e["id"])


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def edenai_llm() -> EdenAILLM:
    api_key = os.environ["EDEN_AI_PRODUCTION_API_TOKEN"]
    base_url = os.getenv("EDEN_AI_BASE_URL", DEFAULT_BASE_URL) + "/v3/llm"
    model = os.getenv("EVAL_JUDGE_MODEL", DEFAULT_MODEL)
    return EdenAILLM(api_key=api_key, base_url=base_url, model=model)


@pytest.fixture(scope="session")
def mintlify_answers(request: pytest.FixtureRequest) -> dict[str, str]:
    """Fetch (or load cached) Mintlify Ask AI answers for every question.

    Answers are cached to ``evals/.cache/answers.json`` so metrics can be
    re-run without hitting the Mintlify API each time.  Use
    ``--refresh-answers`` to force a re-fetch.
    """
    refresh = request.config.getoption("--refresh-answers")

    if not refresh and ANSWERS_CACHE.exists():
        with open(ANSWERS_CACHE) as f:
            return json.load(f)

    api_key = os.getenv("MINTLIFY_API_KEY")
    if not api_key:
        pytest.skip("MINTLIFY_API_KEY not set and no cached answers available")

    answers: dict[str, str] = {}
    with httpx.Client(timeout=60) as client:
        for entry in DATASET_ENTRIES:
            qid = entry["id"]
            answers[qid] = ask_mintlify(entry["question"], api_key, client=client)

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with open(ANSWERS_CACHE, "w") as f:
        json.dump(answers, f, indent=2)

    return answers


@pytest.fixture(scope="session")
def doc_contexts() -> dict[str, list[str]]:
    """Load retrieval contexts from .mdx source docs."""
    contexts: dict[str, list[str]] = {}
    for entry in DATASET_ENTRIES:
        contexts[entry["id"]] = load_doc_context(entry["source_doc"])
    return contexts
