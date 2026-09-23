"""Every link on a published page, and where it points.

One place decides what a link is, because the checks that follow disagree
about nothing else. The rules that matter are all about what to *ignore*: an
MDX page documents MDX, so it contains link markup that is an example rather
than a link, and a code fence contains comments that start with # and are not
headings. Both are blanked before anything is extracted.

Blanking rather than deleting is deliberate. A failure has to name the line in
the file the author will open, so every line the page has survives, empty.
"""

import json
import re
from collections.abc import Iterable, Iterator
from pathlib import Path

from tests.snippet_extractor import DOCS_ROOT, mdx_files

DOCS_JSON = DOCS_ROOT / "docs.json"
SNIPPETS_DIR = DOCS_ROOT / "snippets"

# Two anchors on the site are click targets rather than section links, so no
# heading will ever match them. Each names the script that gives it behaviour,
# and test_links.py reads that script to confirm it really does, so this
# cannot quietly become the place a broken anchor goes to be forgiven.
JS_HOOK_ANCHORS = {
    "chat": "intercom-chat.js",
    "manage-cookies": "cookie-consent.js",
}

# Opening and closing fences look the same, so the scanner toggles on each.
# Both may be indented, inside a <Step> or an <Accordion>.
_FENCE_RE = re.compile(r"^[ \t]*```")
_INLINE_CODE_RE = re.compile(r"`[^`\n]*`")

# The two ways a page links to anything: markdown, and an href or src on a
# component. Mintlify components take the target as a plain string attribute.
_LINK_RE = re.compile(
    r"\]\((?P<markdown>[^)\s]+)\)" r'|(?:href|src)="(?P<attribute>[^"]+)"'
)

_HEADING_RE = re.compile(
    r"^[ \t]{0,3}#{1,6}[ \t]+(?P<text>.+?)[ \t]*#*[ \t]*$", re.MULTILINE
)

# A heading may link out; the anchor is built from the words, not the markup.
_MARKDOWN_LINK_RE = re.compile(r"\[(?P<label>[^\]]*)\]\([^)]*\)")

# github-slugger, which is what Mintlify publishes, keeps word characters,
# hyphens and spaces and drops the rest. Confirmed against the rendered page:
# "Extended Thinking (Claude)" is served as id="extended-thinking-claude", so
# the parentheses go and the word inside them stays.
_SLUG_DROP_RE = re.compile(r"[^\w\- ]", re.UNICODE)

_ASSET_SUFFIXES = frozenset(
    {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".ico", ".pdf", ".mp4"}
)


def readable_text(content: str) -> str:
    """The page with its code blanked out and its line numbering intact."""
    lines = []
    in_fence = False
    for line in content.splitlines(keepends=True):
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            lines.append("\n" if line.endswith("\n") else "")
        elif in_fence:
            lines.append("\n" if line.endswith("\n") else "")
        else:
            lines.append(_INLINE_CODE_RE.sub(lambda m: " " * len(m.group()), line))
    return "".join(lines)


def slugify(heading: str) -> str:
    """The anchor Mintlify gives a heading."""
    text = _MARKDOWN_LINK_RE.sub(r"\g<label>", heading)
    return _SLUG_DROP_RE.sub("", text.lower().strip()).replace(" ", "-")


def heading_slugs(mdx_path: Path) -> set[str]:
    """Every anchor a reader can link to on this page."""
    content = readable_text(mdx_path.read_text(encoding="utf-8"))
    return {slugify(match.group("text")) for match in _HEADING_RE.finditer(content)}


def _kind(target: str) -> str:
    if target.startswith(("http://", "https://")):
        return "external"
    path = target.split("#", 1)[0]
    if Path(path).suffix.lower() in _ASSET_SUFFIXES:
        return "asset"
    return "page"


def _source_name(mdx_path: Path) -> str:
    try:
        return str(mdx_path.relative_to(DOCS_ROOT))
    except ValueError:
        return mdx_path.name


def extract_links(mdx_path: Path) -> list[dict]:
    """Every link on one page, with the line the author will go and look at."""
    content = readable_text(mdx_path.read_text(encoding="utf-8"))
    source_name = _source_name(mdx_path)

    links = []
    for match in _LINK_RE.finditer(content):
        target = match.group("markdown") or match.group("attribute")
        path, _, anchor = target.partition("#")
        links.append(
            {
                "source_mdx": source_name,
                "source_path": str(mdx_path),
                "line": content.count("\n", 0, match.start()) + 1,
                "target": target,
                "kind": _kind(target),
                # Set for a link to a section, whether on this page or another.
                "anchor": anchor,
                # A bare "#section" points at the page it is written on.
                "same_page": path == "",
            }
        )
    return links


def resolve_target(link: dict) -> Path | None:
    """The file a link lands on, or None if it lands nowhere.

    A link to a directory lands on its index, which is how the feature
    reference is reachable without being a navigation entry of its own.
    """
    if link["kind"] == "external":
        return None

    source = Path(link["source_path"])
    if link["same_page"]:
        return source

    path = link["target"].split("#", 1)[0]
    if path.startswith("/"):
        base = DOCS_ROOT / path.lstrip("/")
    else:
        base = (source.parent / path).resolve()

    if link["kind"] == "asset":
        return base if base.is_file() else None

    for candidate in (base.parent / f"{base.name}.mdx", base / "index.mdx", base):
        if candidate.is_file():
            return candidate
    return None


def link_sources() -> list[Path]:
    """Every file whose links reach a reader.

    The published pages, plus the snippets they import: a snippet is not a
    page, but a broken link in one is a broken link on all hundred pages that
    include it.
    """
    return [*mdx_files(), *sorted(SNIPPETS_DIR.glob("*.mdx"))]


def all_links() -> list[dict]:
    """Every link in the published documentation."""
    return [link for path in link_sources() for link in extract_links(path)]


def _entries(node: object) -> Iterator[tuple[str, object]]:
    """Every key and value anywhere in docs.json.

    The navigation is tabs holding groups holding groups, and its shape
    changes whenever a tab is added, so everything below looks for the key it
    cares about rather than for a path through the file.
    """
    if isinstance(node, dict):
        for key, value in node.items():
            yield key, value
            yield from _entries(value)
    elif isinstance(node, list):
        for item in node:
            yield from _entries(item)


def _config_entries() -> list[tuple[str, object]]:
    return list(_entries(json.loads(DOCS_JSON.read_text(encoding="utf-8"))))


def nav_pages() -> list[str]:
    """Every page docs.json puts in the navigation, in the order it lists them."""
    pages = [
        page
        for key, value in _config_entries()
        if key == "pages"
        for page in value
        if isinstance(page, str)
    ]
    return list(dict.fromkeys(pages))


def openapi_specs() -> list[str]:
    """Every OpenAPI document an API reference tab is rendered from.

    Read from docs.json rather than written down here, so a third API gets
    checked by adding it to the navigation and nothing else.
    """
    return _unique_urls(value for key, value in _config_entries() if key == "openapi")


def config_urls() -> list[str]:
    """The addresses docs.json itself sends a reader to, in the navbar and footer."""
    return _unique_urls(
        value for key, value in _config_entries() if key in {"href", "url"}
    )


def external_urls() -> list[str]:
    """Every address the documentation sends a reader to, pages and chrome alike."""
    from_pages = (link["target"] for link in all_links() if link["kind"] == "external")
    return _unique_urls([*from_pages, *config_urls()])


def _unique_urls(values: Iterable[object]) -> list[str]:
    urls = [
        value
        for value in values
        if isinstance(value, str) and value.startswith(("http://", "https://"))
    ]
    return sorted(dict.fromkeys(urls))


def linked_pages() -> set[str]:
    """Every page some other page links to, named as docs.json would name it."""
    reachable = set()
    for link in all_links():
        if link["kind"] != "page" or link["same_page"]:
            continue
        target = resolve_target(link)
        if target is not None:
            reachable.add(str(target.relative_to(DOCS_ROOT))[: -len(".mdx")])
    return reachable
