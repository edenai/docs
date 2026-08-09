import re
from pathlib import Path
from urllib.parse import urlparse

import pytest
import requests

DOCS_ROOT = Path(__file__).resolve().parent.parent

OPENAPI_SPEC_URLS = [
    "https://api.edenai.run/v3/docs/openapi.json",
    "https://api.edenai.run/v2/info/splitted-schema/cost_management/openapi.json",
    "https://api.edenai.run/v2/info/splitted-schema/user/openapi.json",
]

ENDPOINT_URL_RE = re.compile(
    r"https://api\.edenai\.run(?P<path>/v[23][^\s,'\"`)>]*)"
)

_NON_ENDPOINT_SUFFIXES = (".json", ".yaml", ".yml", ".txt", ".md")


@pytest.fixture(scope="session")
def openapi_specs() -> dict[str, dict]:
    specs: dict[str, dict] = {}
    for url in OPENAPI_SPEC_URLS:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        specs[url] = resp.json()
    return specs


@pytest.fixture(scope="session")
def openapi_paths(openapi_specs: dict[str, dict]) -> set[str]:
    all_paths: set[str] = set()
    for spec in openapi_specs.values():
        servers = spec.get("servers") or [{"url": ""}]
        server_prefix = urlparse(servers[0].get("url", "")).path.rstrip("/")
        for spec_path in spec.get("paths", {}).keys():
            all_paths.add((server_prefix + spec_path).rstrip("/"))
    return all_paths


@pytest.mark.parametrize("spec_url", OPENAPI_SPEC_URLS)
def test_openapi_spec_reachable_and_valid(spec_url: str) -> None:
    resp = requests.get(spec_url, timeout=30)
    assert resp.status_code == 200, f"{spec_url} returned {resp.status_code}"
    spec = resp.json()
    assert isinstance(spec, dict), f"{spec_url} did not return a JSON object"
    assert "openapi" in spec or "swagger" in spec, (
        f"{spec_url} is not an OpenAPI/Swagger document"
    )
    paths = spec.get("paths")
    assert isinstance(paths, dict) and paths, f"{spec_url} has no paths"


def _prose_pages() -> list[str]:
    return sorted(
        str(p.relative_to(DOCS_ROOT))
        for p in list(DOCS_ROOT.glob("v3/**/*.mdx")) + list(DOCS_ROOT.glob("*.mdx"))
        if not str(p.relative_to(DOCS_ROOT)).startswith("api-reference/")
    )


def _is_endpoint_path(path: str) -> bool:
    normalized = path.rstrip("/")
    if normalized in ("/v2", "/v3"):
        return False
    if "..." in normalized:
        return False
    return not normalized.endswith(_NON_ENDPOINT_SUFFIXES)


def _matches_openapi_path(path: str, openapi_paths: set[str]) -> bool:
    normalized = path.split("?")[0].split("#")[0].rstrip("/")
    if normalized in openapi_paths:
        return True
    for spec_path in openapi_paths:
        if "{" not in spec_path:
            continue
        pattern = re.sub(r"\{[^/]+\}", r"[^/]+", spec_path.rstrip("/"))
        if re.fullmatch(pattern, normalized):
            return True
    return False


@pytest.mark.parametrize("page", _prose_pages())
def test_prose_endpoint_urls_match_openapi(page: str, openapi_paths: set[str]) -> None:
    content = (DOCS_ROOT / page).read_text(encoding="utf-8")
    unknown: list[str] = []
    for match in ENDPOINT_URL_RE.finditer(content):
        raw_path = match.group("path").split("?")[0].split("#")[0]
        if not _is_endpoint_path(raw_path):
            continue
        if _matches_openapi_path(raw_path, openapi_paths):
            continue
        line = content[: match.start()].count("\n") + 1
        unknown.append(f"line {line}: {match.group(0)}")
    if unknown:
        pytest.fail(f"{page}:\n  " + "\n  ".join(unknown))
