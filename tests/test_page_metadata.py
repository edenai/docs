"""Checks the title and description of every page, the parts that can be counted.

CLAUDE.md ("Page Titles and Descriptions") says how to write a title for
search, and CodeRabbit reviews the judgment in it: whether a title names what
people search for. The rules below are the ones with a right answer, so a test
holds them rather than a reviewer reading prose:

  - Every page declares a title and a description. Without a title Mintlify
    falls back to the file name, which nobody chose.
  - A title is at most 40 characters. Mintlify appends " - Eden AI
    Documentation", 24 more, and Google cuts a result at around 60.
  - No two pages share a title, or they compete for the same search.
  - <TechArticleSchema> repeats the title, the description and the page's own
    path exactly. It adds a second structured-data block beside the one
    Mintlify builds from the frontmatter, so a copy a retitle leaves behind
    gives Google two different headlines for one page.

The description's length stays review guidance rather than a check: most
pages are outside the 120 to 160 characters CLAUDE.md asks of a new one.
"""

from collections import defaultdict
from pathlib import Path

import pytest

from tests.page_metadata import frontmatter, schema_props
from tests.snippet_extractor import DOCS_ROOT, mdx_files

TITLE_MAX = 40

_PAGES = mdx_files()
_META = {page: frontmatter(page) for page in _PAGES}
_SCHEMAS = {page: props for page in _PAGES if (props := schema_props(page)) is not None}


def _name(page: Path) -> str:
    """The page as docs.json names it."""
    return page.relative_to(DOCS_ROOT).with_suffix("").as_posix()


# --- the docs as they stand ------------------------------------------------


@pytest.mark.parametrize("page", _PAGES, ids=_name)
def test_a_page_declares_its_title_and_description(page):
    missing = [key for key in ("title", "description") if not _META[page].get(key)]
    assert missing == [], (
        f"{_name(page)}.mdx has no {' or '.join(missing)} in its frontmatter"
    )


@pytest.mark.parametrize("page", _PAGES, ids=_name)
def test_a_title_fits_in_a_search_result(page):
    title = _META[page].get("title", "")
    assert len(title) <= TITLE_MAX, (
        f'{_name(page)}.mdx is titled "{title}", {len(title)} characters. '
        f"Keep it to {TITLE_MAX}, and put a longer sidebar label in sidebarTitle"
    )


def test_no_two_pages_share_a_title():
    pages_by_title = defaultdict(list)
    for page, meta in _META.items():
        if meta.get("title"):
            pages_by_title[meta["title"].casefold()].append(_name(page))
    shared = {title: pages for title, pages in pages_by_title.items() if len(pages) > 1}
    assert shared == {}, f"these pages share a title: {shared}"


@pytest.mark.parametrize("page", list(_SCHEMAS), ids=_name)
def test_the_structured_data_repeats_the_frontmatter(page):
    meta = _META[page]
    expected = {
        "title": meta.get("title"),
        "description": meta.get("description"),
        "path": _name(page),
    }
    actual = {key: _SCHEMAS[page].get(key) for key in expected}
    assert actual == expected, (
        f"<TechArticleSchema> on {_name(page)}.mdx disagrees with the page; "
        "change both copies together"
    )


# --- the checks can fail ---------------------------------------------------


def test_each_way_of_writing_a_prop_is_read(tmp_path):
    page = tmp_path / "page.mdx"
    page.write_text(
        '---\ntitle: "Static IP"\n---\n\n<TechArticleSchema\n'
        '  title={"Static IP"}\n'
        "  description={`Uses \\`code\\` and \\${x}`}\n"
        '  path="v3/data-governance/static-ip"\n'
        "/>\n"
    )

    assert frontmatter(page) == {"title": "Static IP"}
    assert schema_props(page) == {
        "title": "Static IP",
        "description": "Uses `code` and ${x}",
        "path": "v3/data-governance/static-ip",
    }


def test_a_page_without_structured_data_has_no_props(tmp_path):
    page = tmp_path / "page.mdx"
    page.write_text('---\ntitle: "EU Endpoint"\n---\n\nNo schema here.\n')

    assert schema_props(page) is None


def test_the_docs_still_contain_the_pages_these_checks_claim_to_cover():
    """A change to the readers that finds nothing would pass every check above."""
    assert len(_PAGES) > 100
    assert len(_SCHEMAS) > 100
