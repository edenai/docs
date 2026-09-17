"""Check that every model the docs name still exists in the live catalogue.

The docs go stale silently here. A provider is dropped, a preview model is
renamed at GA, a version is superseded, and the page keeps recommending an id
the API now rejects. Nothing in the snippet suite catches it, because a wrong
id usually sits in a prose table or a comparison list rather than in a
runnable block.

Both catalogues are public, so these checks need no credentials and spend
nothing. They read:

* the seven ``/v3/**/models`` listings, which between them hold every LLM id.
  ``/v3/models`` alone is chat-only, so checking it on its own reports every
  embedding, image, audio and video model as missing.
* ``/v3/info``, which holds the expert-model ``feature/subfeature/provider``
  paths and the optional ``/model`` suffix.

Only fragments whose first segment names a known feature or a known LLM
provider are checked. A fragment that looks like neither is left alone rather
than guessed at, so a provider typo (``anthropc/claude-sonnet-5``) reads as an
unknown namespace and passes. Catching those needs a way to tell a model id
from any other slash-separated word in prose, which the backtick alone does
not give.
"""

import json
import re
from pathlib import Path
from typing import NamedTuple

import pytest
import requests
from filelock import FileLock
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

from tests.snippet_extractor import DOCS_ROOT, mdx_files

# Pinned to production on purpose, and deliberately not reading
# EDEN_AI_BASE_URL like the rest of the suite. The catalogue is per
# environment and the docs document the production one, so honouring a staging
# override here would report almost every id in the tree as missing.
CATALOGUE_BASE_URL = "https://api.edenai.run"
_TIMEOUT = 60
_HINT_LIMIT = 4
_CACHE_FILE = "model-catalogue.json"

# /v3/models is hardcoded to the chat routes. The rest of the catalogue lives
# behind these siblings, all sharing the {"data": [{"id": ...}]} shape.
_MODEL_ROUTES = (
    "/v3/models",
    "/v3/embeddings/models",
    "/v3/moderations/models",
    "/v3/images/models",
    "/v3/audio/transcriptions/models",
    "/v3/audio/speech/models",
    "/v3/videos/models",
)

_BACKTICKED = re.compile(r"`([^`\n]+)`")

# A backticked fragment is a candidate id only if it could be one verbatim.
# Anything carrying placeholder or wildcard syntax is documenting a shape, not
# naming a model: `audio/tts/{provider}[/{model}]`, `anthropic/*`.
_NOT_A_LITERAL_ID = set("{}[]<>*()")


class Catalogue(NamedTuple):
    """Every name the API will currently answer to."""

    model_ids: set[str]
    live_for_scope: dict[str, set[str]]
    feature_names: set[str]
    llm_providers: set[str]


def _fetch_catalogue() -> dict:
    """Read the live catalogue, as plain JSON-safe types."""
    session = requests.Session()
    # One upstream blip should not fail a docs PR with a stack trace.
    session.mount(
        "https://",
        HTTPAdapter(max_retries=Retry(total=3, backoff_factor=0.5)),
    )

    def get_json(route: str) -> dict:
        response = session.get(f"{CATALOGUE_BASE_URL}{route}", timeout=_TIMEOUT)
        response.raise_for_status()
        return response.json()

    with session:
        model_ids = sorted(
            {
                entry["id"]
                for route in _MODEL_ROUTES
                for entry in get_json(route)["data"]
            }
        )
        features = get_json("/v3/info")["features"]

    return {
        "model_ids": model_ids,
        "live_for_scope": {
            f"{feature['name']}/{subfeature['name']}": sorted(
                m["model"] for m in subfeature.get("models", [])
            )
            for feature in features
            for subfeature in feature.get("subfeatures", [])
        },
        "feature_names": sorted(f["name"] for f in features),
    }


@pytest.fixture(scope="session")
def catalogue(tmp_path_factory) -> Catalogue:
    """Fetch the live catalogue once per run, not once per xdist worker.

    A session fixture runs in every worker process, so with ``-n auto`` the
    plain version hammers the public API with one full catalogue read per core.
    The first worker to arrive fetches and writes the shared basetemp; the rest
    read that file.
    """
    cache = tmp_path_factory.getbasetemp().parent / _CACHE_FILE
    with FileLock(f"{cache}.lock"):
        if cache.exists():
            raw = json.loads(cache.read_text())
        else:
            raw = _fetch_catalogue()
            cache.write_text(json.dumps(raw))

    model_ids = set(raw["model_ids"])
    return Catalogue(
        model_ids=model_ids,
        live_for_scope={k: set(v) for k, v in raw["live_for_scope"].items()},
        feature_names=set(raw["feature_names"]),
        # Deriving the providers from the ids themselves keeps this on v3
        # alone. /v2/info/providers/ lists more, but the extras have no LLM
        # models, so they can never prefix a valid id anyway, and v2 retires.
        llm_providers={i.split("/")[0] for i in model_ids if "/" in i},
    )


def _candidate_ids(text: str):
    """Yield (line number, fragment) for each backticked literal id on a page."""
    for line_number, line in enumerate(text.split("\n"), 1):
        for fragment in _BACKTICKED.findall(line):
            # One backtick span sometimes lists several ids: `a/b,c/d`.
            for part in (p.strip() for p in fragment.split(",")):
                if (
                    "/" in part
                    and " " not in part
                    and not _NOT_A_LITERAL_ID & set(part)
                ):
                    yield line_number, part


def _nearest_ids(wrong: str, model_ids: set[str]) -> list[str]:
    """Live ids sharing the longest stem with a wrong one, for the hint.

    Drops one trailing ``-segment`` at a time, so ``claude-sonnet-99`` offers
    the ``claude-sonnet`` family rather than every id the provider has.
    """
    provider, _, name = wrong.partition("/")
    segments = name.split("-")
    for cut in range(len(segments), 0, -1):
        stem = f"{provider}/{'-'.join(segments[:cut])}"
        matches = sorted(i for i in model_ids if i.startswith(stem))
        if matches:
            return matches[:_HINT_LIMIT]
    return []


def _unresolved(fragment: str, catalogue: Catalogue) -> str | None:
    """Say why the fragment names nothing live, or None if it resolves."""
    head, *rest = fragment.split("/")

    if head in catalogue.feature_names:
        if len(rest) < 2:
            # feature/subfeature on its own names a route, not a model.
            return None
        scope = f"{head}/{rest[0]}"
        live = catalogue.live_for_scope.get(scope)
        if live is None:
            return f"no such subfeature as {scope}"
        if fragment in live:
            return None
        names = sorted(p.split("/", 2)[2] for p in live)
        return f"live for {scope}: {', '.join(names) or 'nothing'}"

    if head in catalogue.llm_providers and fragment not in catalogue.model_ids:
        near = _nearest_ids(fragment, catalogue.model_ids)
        return f"closest ids: {', '.join(near)}" if near else "no similar id"

    return None


@pytest.mark.parametrize(
    "mdx_path", mdx_files(), ids=lambda p: str(p.relative_to(DOCS_ROOT))
)
def test_page_names_only_live_models(mdx_path: Path, catalogue: Catalogue):
    """Every model id and expert-model path on the page resolves."""
    unknown = [
        (line_number, fragment, hint)
        for line_number, fragment in _candidate_ids(
            mdx_path.read_text(encoding="utf-8")
        )
        if (hint := _unresolved(fragment, catalogue)) is not None
    ]

    if unknown:
        report = "\n".join(
            f"  line {line}: {fragment}\n      {hint}"
            for line, fragment, hint in unknown
        )
        pytest.fail(
            f"{mdx_path.relative_to(DOCS_ROOT)} names "
            f"{len(unknown)} model(s) the API does not have:\n{report}"
        )
