import json
import os
import re
import time
from functools import cache
from pathlib import Path
from urllib.parse import urldefrag, urlparse

import pytest
import requests

DOCS_ROOT = Path(__file__).resolve().parent.parent

FENCED_BLOCK_RE = re.compile(r"^```.*?^```", re.MULTILINE | re.DOTALL)
MARKDOWN_LINK_RE = re.compile(r"\[[^\]]*\]\((?P<url>[^)\s]+)(?:\s+\"[^\"]*\")?\)")
JSX_HREF_RE = re.compile(r"\bhref\s*=\s*[\"'](?P<url>[^\"'#][^\"']*)[\"']")
SCHEMA_PATH_RE = re.compile(r"\bpath\s*=\s*[\"'](?P<url>[^\"']+)[\"']")
BARE_URL_RE = re.compile(r"(?<![\"'`(=])(?P<url>https?://[^\s'\"`)>\]]+)")

REQUEST_TIMEOUT_SECONDS = 10
MAX_RETRIES = 3
USER_AGENT = (
    "Mozilla/5.0 (compatible; edenai-docs-linkcheck/1.0; +https://docs.edenai.co)"
)

SKIP_EXTERNAL_HOSTS = frozenset(
    {"localhost", "127.0.0.1", "example.com"}
)


def _strip_fenced_blocks(content: str) -> str:
    return FENCED_BLOCK_RE.sub("", content)


def _pages() -> list[str]:
    return sorted(
        str(p.relative_to(DOCS_ROOT))
        for p in list(DOCS_ROOT.glob("v3/**/*.mdx")) + list(DOCS_ROOT.glob("*.mdx"))
        if not str(p.relative_to(DOCS_ROOT)).startswith("api-reference/")
    )


def _extract_links(page: str) -> list[dict]:
    raw = (DOCS_ROOT / page).read_text(encoding="utf-8")
    body = _strip_fenced_blocks(raw)
    links: list[dict] = []
    seen: set[str] = set()

    def add(url: str, offset: int) -> None:
        if url in seen:
            return
        seen.add(url)
        links.append({"url": url, "line": raw[:offset].count("\n") + 1})

    for match in MARKDOWN_LINK_RE.finditer(body):
        add(match.group("url"), match.start())
    for match in JSX_HREF_RE.finditer(body):
        add(match.group("url"), match.start())
    for match in SCHEMA_PATH_RE.finditer(body):
        add(match.group("url"), match.start())
    for match in BARE_URL_RE.finditer(body):
        add(match.group("url"), match.start())
    return links


def _resolve_internal(source_page: str, link: str) -> Path:
    target, _ = urldefrag(link.split("?", 1)[0])
    if not target:
        return DOCS_ROOT / source_page

    if target.startswith("/"):
        candidates = [DOCS_ROOT / target.lstrip("/")]
    elif target.startswith(("./", "../")):
        candidates = [(DOCS_ROOT / source_page).parent / target]
    else:
        candidates = [
            DOCS_ROOT / target,
            (DOCS_ROOT / source_page).parent / target,
        ]

    for base in candidates:
        if base.suffix in {".mdx", ".md"} and base.exists():
            return base
        for suffix in (".mdx", ".md"):
            with_ext = base.with_suffix(suffix)
            if with_ext.exists():
                return with_ext
    return candidates[0]


def _is_external(link: str) -> bool:
    parsed = urlparse(link)
    return parsed.scheme in {"http", "https"}


def _is_checkable(link: str) -> bool:
    parsed = urlparse(link)
    if parsed.scheme in {"mailto", "tel", "javascript"}:
        return False
    if not parsed.scheme and not parsed.netloc and not parsed.path:
        return False
    if parsed.scheme in {"http", "https"} and parsed.hostname in SKIP_EXTERNAL_HOSTS:
        return False
    return True


DEFINITELY_BROKEN_STATUSES = frozenset({404, 410})


@cache
def _check_external(url: str) -> tuple[bool, str]:
    headers = {"User-Agent": USER_AGENT}
    last_status = "no attempt"
    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.head(
                url, headers=headers, allow_redirects=True, timeout=REQUEST_TIMEOUT_SECONDS
            )
            if resp.status_code in {400, 403, 405, 501}:
                resp = requests.get(
                    url,
                    headers=headers,
                    allow_redirects=True,
                    timeout=REQUEST_TIMEOUT_SECONDS,
                    stream=True,
                )
                resp.close()
        except requests.RequestException as exc:
            last_status = f"network error: {exc.__class__.__name__}"
            time.sleep(2**attempt)
            continue
        if resp.status_code == 429:
            wait = int(resp.headers.get("Retry-After", "1"))
            time.sleep(min(wait, 5))
            continue
        if resp.status_code in DEFINITELY_BROKEN_STATUSES:
            return False, f"HTTP {resp.status_code}"
        if 500 <= resp.status_code < 600:
            last_status = f"HTTP {resp.status_code}"
            time.sleep(2**attempt)
            continue
        return True, str(resp.status_code)
    return False, last_status


@pytest.mark.parametrize("page", _pages())
def test_page_links(page: str) -> None:
    broken: list[str] = []
    for link in _extract_links(page):
        url = link["url"]
        if not _is_checkable(url):
            continue
        if _is_external(url):
            ok, detail = _check_external(url)
            if not ok:
                broken.append(f"line {link['line']}: external {url} ({detail})")
        else:
            target = _resolve_internal(page, url)
            if not target.exists():
                broken.append(f"line {link['line']}: internal {url} -> {target.relative_to(DOCS_ROOT)} (missing)")
    if broken:
        pytest.fail(f"{page}:\n  " + "\n  ".join(broken))


def _collect_docs_json_pages(node: object) -> list[str]:
    found: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "pages" and isinstance(value, list):
                for item in value:
                    if isinstance(item, str):
                        found.append(item)
                    else:
                        found.extend(_collect_docs_json_pages(item))
            elif key != "openapi":
                found.extend(_collect_docs_json_pages(value))
    elif isinstance(node, list):
        for item in node:
            found.extend(_collect_docs_json_pages(item))
    return found


def test_docs_json_nav_paths() -> None:
    docs_json = json.loads((DOCS_ROOT / "docs.json").read_text(encoding="utf-8"))
    broken: list[str] = []
    for path in _collect_docs_json_pages(docs_json):
        if path.startswith(("http://", "https://", "#")):
            continue
        candidate_mdx = DOCS_ROOT / f"{path.lstrip('/')}.mdx"
        candidate_md = DOCS_ROOT / f"{path.lstrip('/')}.md"
        if not candidate_mdx.exists() and not candidate_md.exists():
            broken.append(f"docs.json nav path `{path}` -> file missing")
    if broken:
        pytest.fail("docs.json:\n  " + "\n  ".join(broken))
