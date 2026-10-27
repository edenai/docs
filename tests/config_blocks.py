"""The configuration blocks on the integration pages, and the names in them.

An integration page tells a reader to point some other program at Eden AI, and
what it gives them is a file to paste: a JSON, YAML or TOML config that
Continue, Kilo Code, LibreChat, Codex CLI or OpenCode reads. No runner can
help, because there is no program here to run. What can be wrong with a config
is its syntax and the names inside it, so those are what this extracts.

Deciding what is a model id is the whole problem, and it is decided by data
rather than by a list. A config block is full of strings with a slash in them
that are not models: docker volume mounts, image tags, MIME types, URLs. Two
rules separate them. The shape rule drops anything that cannot be an id at
all, and then the provider rule keeps only what begins with a provider Eden AI
actually has, which the catalog itself supplies. That is why "image/gif" is
not a model reference and nothing had to say so.

The catalog is the union of seven routes. /v3/models is hardcoded to the chat
endpoints, so it lists chat models only, and a config block may name any of
the rest: Continue configures an embeddings model next to its chat models, and
checking that one against /v3/models alone would call it broken.
"""

import hashlib
import json
import os
import re
import tomllib
from concurrent.futures import ThreadPoolExecutor
from functools import cache
from pathlib import Path
from typing import Any

import requests
import yaml
from filelock import FileLock
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

from tests.helpers.http import TIMEOUT, url_exists
from tests.snippet_extractor import DOCS_ROOT, extract_config_blocks

__all__ = [
    "CATALOG_BASE_URL",
    "CATALOG_CACHE_VAR",
    "CONFIG_LANGUAGES",
    "INTEGRATIONS_DIR",
    "MODEL_CATALOG_ROUTES",
    "TOOL_PREFIX",
    "catalog_ids",
    "catalog_providers",
    "catalog_routes",
    "config_blocks",
    "config_pages",
    "eden_urls",
    "model_candidates",
    "model_references",
    "models_in",
    "normalize_model_id",
    "parse_config",
    "url_exists",
    "url_probe",
]

CONFIG_LANGUAGES = ("json", "yaml", "yml", "toml")

# The integration section is where a reader is handed somebody else's config
# file. A JSON fence elsewhere in the docs is an API response being shown, not
# a file to paste, and parsing those would check nothing.
INTEGRATIONS_DIR = DOCS_ROOT / "v3" / "integrations"

CATALOG_BASE_URL = "https://api.edenai.run/v3"

# Where a run keeps the catalog once one process has fetched it. conftest points
# it at the session's temp directory, which every xdist worker shares.
CATALOG_CACHE_VAR = "_EDEN_CATALOG_CACHE_DIR"

# A rate limit or a passing 5xx on any one of the catalog requests would
# otherwise error the collection of every test built from the catalog.
_CATALOG_RETRY = Retry(
    total=3, backoff_factor=1, status_forcelist=(429, 500, 502, 503, 504)
)

MODEL_CATALOG_ROUTES = (
    "models",
    "embeddings/models",
    "moderations/models",
    "images/models",
    "audio/transcriptions/models",
    "audio/speech/models",
    "videos/models",
)

# OpenCode and Kilo Code write the name of the provider they configured, then
# the Eden AI id, which contains a slash of its own. Those tools split on the
# first slash only, so that is what happens here.
TOOL_PREFIX = "edenai/"

# Anything that could be "a/b" or "a/b/c". Run over the raw text rather than a
# parsed document, because a block that is a menu of alternatives does not
# parse and its model ids still have to be checked. It never ends on a period,
# because no id does and a sentence that ends on one does.
_CANDIDATE_RE = re.compile(r"[A-Za-z0-9_.@-]+(?:/[A-Za-z0-9_.@-]+)+(?<!\.)")

# A JavaScript module path has the shape of an id and can start with a
# provider: import type { X } from 'openai/resources/chat/completions', or
# await import('openai/resources/chat').
_MODULE_SPECIFIER_RE = re.compile(r"""(?:\bfrom|\bimport\(?|\brequire\()\s*["']$""")

# A provider is a lowercase word. This is what rejects an image tag
# (ghcr.io/...), a path (./data/...) and a host (api.edenai.run/v3), all of
# which carry a dot where a provider never does.
_PROVIDER_SEGMENT_RE = re.compile(r"^[a-z0-9_]+$")

_EDEN_URL_RE = re.compile(r"https://api(?:\.eu)?\.edenai\.run[A-Za-z0-9/_.-]*")

# Almost every config sets a base URL rather than an endpoint, because the
# tool appends the path itself. A base URL answers 404 on its own and always
# will, so asking whether it resolves answers nothing. What a tool relies on
# is that the API is underneath it, and /models is the request those tools
# make first, so that is the one worth making.
_BASE_URL_RE = re.compile(r"^https://api(?:\.eu)?\.edenai\.run/v\d+/?$")

_PARSERS = {
    "json": json.loads,
    "yaml": yaml.safe_load,
    "yml": yaml.safe_load,
    "toml": tomllib.loads,
}


def config_pages() -> list[Path]:
    """The integration pages, in a stable order."""
    return sorted(INTEGRATIONS_DIR.glob("*.mdx"))


def config_blocks() -> list[dict]:
    """Every config block on every integration page, with its origin."""
    blocks = []
    for page in config_pages():
        source_mdx = str(page.relative_to(DOCS_ROOT))
        for block in extract_config_blocks(page):
            blocks.append({**block, "source_mdx": source_mdx, "source_path": page})
    return blocks


def parse_config(lang: str, code: str) -> Any:
    """The block as the tool that reads it would see it.

    Raises whatever the parser raises, because the message it writes names the
    line and the column and no wrapper improves on that.
    """
    return _PARSERS[lang](code)


def normalize_model_id(value: str) -> str:
    """The Eden AI id, with any configured provider name taken off the front."""
    if value.startswith(TOOL_PREFIX):
        return value[len(TOOL_PREFIX) :]
    return value


def _candidates_in(text: str) -> list[str]:
    """Strings shaped like a model id, in the order the text has them."""
    candidates = []
    for match in _CANDIDATE_RE.finditer(text):
        if _MODULE_SPECIFIER_RE.search(text, 0, match.start()):
            continue
        token = match.group(0)
        provider = normalize_model_id(token).split("/", 1)[0]
        if _PROVIDER_SEGMENT_RE.match(provider):
            candidates.append(token)
    return candidates


def model_candidates(block: dict) -> set[str]:
    """Strings in the block shaped like a model id.

    Shape only, so this needs no network and says nothing about whether the
    model exists. A docker mount and a MIME type can still get through here;
    model_references is what settles it.
    """
    return set(_candidates_in(block["code"]))


def models_in(text: str) -> list[str]:
    """The model references in any text, in order and each once.

    The same two rules as model_references, for text that is not a config
    block: a shell block, a table cell, a sentence naming the model to pick.
    Order is kept because the first model a page names is the one it leads
    with, which is the one worth sending a request to.
    """
    providers = catalog_providers()
    seen: dict[str, None] = {}
    for candidate in _candidates_in(text):
        if normalize_model_id(candidate).split("/", 1)[0] in providers:
            seen.setdefault(candidate)
    return list(seen)


def model_references(block: dict) -> set[str]:
    """The candidates that begin with a provider Eden AI really has."""
    return set(models_in(block["code"]))


def eden_urls(block: dict) -> set[str]:
    """Every Eden AI address the block points at."""
    return set(_EDEN_URL_RE.findall(block["code"]))


def url_probe(url: str) -> str:
    """The address to request in order to judge the one written down."""
    if _BASE_URL_RE.match(url):
        return f"{url.rstrip('/')}/models"
    return url


def catalog_routes(base_url: str = CATALOG_BASE_URL) -> dict[str, dict[str, dict]]:
    """Every model Eden AI serves, under the catalog route that lists it.

    The route is what says which request a model answers: an id under
    embeddings/models takes an embeddings call and nothing else. Each entry is
    kept whole, because the chat entries carry the capabilities a tool relies
    on, function calling first among them.

    Production's unless a caller names another API: readers use production,
    so that is the catalog a page is checked against.
    """
    return _catalog_routes(base_url)


@cache
def _catalog_routes(base_url: str) -> dict[str, dict[str, dict]]:
    cache_dir = os.environ.get(CATALOG_CACHE_VAR)
    if not cache_dir:
        return _fetch_catalog(base_url)
    # Every xdist worker collects on its own, and the integration tests are
    # parametrized from this. Two workers that fetched it a moment apart could
    # collect different tests, which xdist refuses, so the first one here
    # fetches it for the rest.
    digest = hashlib.sha256(base_url.encode()).hexdigest()[:12]
    path = Path(cache_dir) / f"catalog-{digest}.json"
    with FileLock(f"{path}.lock"):
        if not path.exists():
            path.write_text(json.dumps(_fetch_catalog(base_url)))
        return json.loads(path.read_text())


def _fetch_catalog(base_url: str) -> dict[str, dict[str, dict]]:
    # Fetched together, because seven requests one after another hold up
    # collection.
    with ThreadPoolExecutor(len(MODEL_CATALOG_ROUTES)) as pool:
        entries = pool.map(
            lambda route: _catalog_route(base_url, route), MODEL_CATALOG_ROUTES
        )
        return dict(zip(MODEL_CATALOG_ROUTES, entries))


def _catalog_route(base_url: str, route: str) -> dict[str, dict]:
    with requests.Session() as session:
        session.mount("https://", HTTPAdapter(max_retries=_CATALOG_RETRY))
        response = session.get(f"{base_url}/{route}", timeout=TIMEOUT)
    response.raise_for_status()
    payload = response.json()
    entries = payload["data"] if isinstance(payload, dict) else payload
    return {entry["id"]: entry for entry in entries}


@cache
def catalog_ids() -> frozenset[str]:
    """Every model id Eden AI serves, across all seven catalog routes."""
    return frozenset(
        model_id for entries in catalog_routes().values() for model_id in entries
    )


@cache
def catalog_providers() -> frozenset[str]:
    """The provider half of every id in the catalog."""
    return frozenset(model_id.split("/", 1)[0] for model_id in catalog_ids())
