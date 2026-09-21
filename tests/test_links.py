"""Checks that every link on a published page lands somewhere.

A broken link is the one docs bug a reader always hits and never reports. The
snippet suites cover the code on a page; nothing covered the prose around it,
so a page could be renamed and every link to it kept pointing at a 404.

These checks read files and make no requests, so they run on every pull
request next to the syntax checks. The links that need the network, the
external URLs and the two OpenAPI specs the API reference renders from, live
in test_links_external.py.

What a link *is* turns out to be the whole problem. Three things in this repo
look like broken links and are not, and each one is a rule below:

  - MDX pages document MDX, so a code fence contains link markup that is an
    example, not a link. tests/links.py blanks fenced and inline code first.
  - A Python comment inside a fence starts with #, so a heading scan that does
    not blank fences first invents headings, and a real broken anchor then
    resolves against one of them.
  - #chat and #manage-cookies are not headings at all. They are click targets
    bound by intercom-chat.js and cookie-consent.js. The allowlist is checked
    against those files rather than trusted, so it cannot grow a third entry
    that nothing implements.
"""

import json

import pytest

from tests.links import (
    DOCS_JSON,
    JS_HOOK_ANCHORS,
    all_links,
    extract_links,
    heading_slugs,
    linked_pages,
    nav_pages,
    readable_text,
    resolve_target,
    slugify,
)
from tests.snippet_extractor import DOCS_ROOT, mdx_files

_LINKS = all_links()
_PAGE_LINKS = [link for link in _LINKS if link["kind"] == "page"]
# Both a bare "#section" and a "/page#section" have to land on a heading.
_ANCHOR_LINKS = [link for link in _LINKS if link["anchor"]]
_ASSET_LINKS = [link for link in _LINKS if link["kind"] == "asset"]


def _where(link: dict) -> str:
    return f"{link['source_mdx']} line {link['line']}"


def _case_id(link: dict) -> str:
    return f"{link['source_mdx']}::{link['line']}::{link['target']}"


# --- what counts as a link -------------------------------------------------


def test_a_markdown_link_is_found_with_the_line_it_is_on(tmp_path):
    page = tmp_path / "page.mdx"
    page.write_text("intro\n\nsee [the guide](/v3/general/sandbox) for more\n")

    (link,) = extract_links(page)

    assert link["target"] == "/v3/general/sandbox"
    assert link["line"] == 3
    assert link["kind"] == "page"


def test_an_href_on_a_component_is_a_link(tmp_path):
    page = tmp_path / "page.mdx"
    page.write_text('<Card title="Monitoring" href="/v3/general/monitoring" />\n')

    (link,) = extract_links(page)

    assert link["target"] == "/v3/general/monitoring"


def test_link_markup_inside_a_code_fence_is_not_a_link(tmp_path):
    """A page that documents MDX shows link markup as an example of markup."""
    page = tmp_path / "page.mdx"
    page.write_text(
        "real [link](/v3/general/sandbox)\n"
        "\n"
        "```mdx\n"
        '<Card title="Getting started" href="/quickstart">\n'
        "[another](/does-not-exist)\n"
        "```\n"
    )

    targets = [link["target"] for link in extract_links(page)]

    assert targets == ["/v3/general/sandbox"]


def test_link_markup_inside_inline_code_is_not_a_link(tmp_path):
    page = tmp_path / "page.mdx"
    page.write_text("write `[label](/not-a-real-page)` to link a page\n")

    assert extract_links(page) == []


def test_blanking_code_keeps_the_line_numbers_the_page_has(tmp_path):
    """A reported line has to be the line in the file, not in the stripped copy."""
    page = tmp_path / "page.mdx"
    page.write_text("```python\nx = 1\ny = 2\n```\n\n[link](/v3/general/sandbox)\n")

    (link,) = extract_links(page)

    assert link["line"] == 6


def test_a_relative_link_resolves_against_the_page_it_is_on(tmp_path):
    (tmp_path / "opencode.mdx").write_text("# Opencode\n")
    page = tmp_path / "claude-code.mdx"
    page.write_text("see [opencode](./opencode)\n")

    (link,) = extract_links(page)

    assert resolve_target(link) == tmp_path / "opencode.mdx"


def test_a_link_to_a_directory_resolves_to_its_index(tmp_path):
    (tmp_path / "features").mkdir()
    (tmp_path / "features" / "index.mdx").write_text("# Features\n")
    page = tmp_path / "page.mdx"
    page.write_text("see [features](./features)\n")

    (link,) = extract_links(page)

    assert resolve_target(link) == tmp_path / "features" / "index.mdx"


def test_a_link_to_a_page_that_does_not_exist_resolves_to_nothing(tmp_path):
    page = tmp_path / "page.mdx"
    page.write_text("see [nowhere](./nowhere)\n")

    (link,) = extract_links(page)

    assert resolve_target(link) is None


# --- what counts as a heading ----------------------------------------------


def test_a_heading_slug_matches_what_mintlify_publishes():
    """Confirmed against the rendered page, not inferred.

    docs.edenai.co/v3/llms/chat-completions serves the Extended Thinking
    section as id="extended-thinking-claude", so the parenthesised word stays
    and only the punctuation goes.
    """
    assert slugify("Extended Thinking (Claude)") == "extended-thinking-claude"
    assert slugify("Dedicated Support with SLA") == "dedicated-support-with-sla"
    assert slugify("OpenAI Python SDK Integration") == "openai-python-sdk-integration"


def test_a_comment_inside_a_code_fence_is_not_a_heading(tmp_path):
    """Otherwise a broken anchor resolves against a heading nobody wrote."""
    page = tmp_path / "page.mdx"
    page.write_text(
        "## Real Heading\n"
        "\n"
        "```python\n"
        "# Point to Eden AI endpoint\n"
        "client = OpenAI()\n"
        "```\n"
    )

    assert heading_slugs(page) == {"real-heading"}


def test_the_readable_text_of_a_page_drops_code_and_keeps_its_shape(tmp_path):
    page = tmp_path / "page.mdx"
    content = "before\n```python\nsecret = 1\n```\nafter\n"
    page.write_text(content)

    readable = readable_text(content)

    assert "secret" not in readable
    assert readable.count("\n") == content.count("\n")


# --- the docs as they stand ------------------------------------------------


@pytest.mark.parametrize("link", _PAGE_LINKS, ids=[_case_id(b) for b in _PAGE_LINKS])
def test_an_internal_link_points_at_a_page_that_exists(link):
    if resolve_target(link) is None:
        pytest.fail(f"{_where(link)} links to {link['target']}, which is not a page")


@pytest.mark.parametrize(
    "link", _ANCHOR_LINKS, ids=[_case_id(b) for b in _ANCHOR_LINKS]
)
def test_an_anchor_points_at_a_heading_on_the_page_it_names(link):
    anchor = link["anchor"]
    if anchor in JS_HOOK_ANCHORS:
        pytest.skip(f"bound by {JS_HOOK_ANCHORS[anchor]} rather than a heading")

    target = resolve_target(link)
    if target is None:
        pytest.fail(f"{_where(link)} links to {link['target']}, which is not a page")

    slugs = heading_slugs(target)
    if anchor not in slugs:
        pytest.fail(
            f"{_where(link)} links to #{anchor}, and "
            f"{target.relative_to(DOCS_ROOT)} has no such heading. "
            f"It has: {', '.join(sorted(slugs))}"
        )


@pytest.mark.parametrize("link", _ASSET_LINKS, ids=[_case_id(b) for b in _ASSET_LINKS])
def test_an_image_points_at_a_file_in_the_repository(link):
    if resolve_target(link) is None:
        pytest.fail(f"{_where(link)} shows {link['target']}, which is not in the repo")


@pytest.mark.parametrize("page", nav_pages(), ids=lambda p: p)
def test_every_page_in_the_navigation_exists(page):
    """docs.json names a page that was renamed or deleted and the tab 404s."""
    if not (DOCS_ROOT / f"{page}.mdx").is_file():
        if not (DOCS_ROOT / page / "index.mdx").is_file():
            pytest.fail(f"docs.json lists {page}, which has no .mdx file")


def test_every_published_page_is_reachable():
    """A page nobody can navigate to is one nobody reads.

    Reachable means listed in docs.json or linked from a page that is. The
    features index is the second case: it is not a nav entry, and the MCP
    server page links to it.
    """
    listed = set(nav_pages())
    linked = linked_pages()
    unreachable = sorted(
        str(page.relative_to(DOCS_ROOT).with_suffix(""))
        for page in mdx_files()
        if str(page.relative_to(DOCS_ROOT).with_suffix("")) not in listed | linked
    )
    assert unreachable == [], (
        "these pages are published but nothing points at them: "
        + ", ".join(unreachable)
    )


# --- the checks can fail ---------------------------------------------------


def test_every_js_hook_anchor_is_bound_by_the_file_it_names():
    """The allowlist is the one place a real broken anchor could hide.

    An anchor listed here is never checked against a heading, so each entry
    has to name the script that gives it its behaviour, and that script has to
    actually select it.
    """
    for anchor, script in JS_HOOK_ANCHORS.items():
        source = (DOCS_ROOT / script).read_text(encoding="utf-8")
        assert f'href$="#{anchor}"' in source, (
            f"{script} does not bind #{anchor}, so nothing gives that link "
            f"its behaviour and it is simply broken"
        )


def test_a_broken_link_on_a_page_is_reported(tmp_path):
    """The guard above passes today, so prove it is not passing vacuously."""
    page = tmp_path / "page.mdx"
    page.write_text("see [the guide](/v3/general/renamed-away)\n")

    (link,) = extract_links(page)

    assert link["kind"] == "page"
    assert resolve_target(link) is None


def test_a_broken_anchor_is_reported(tmp_path):
    page = tmp_path / "page.mdx"
    page.write_text("## Live Chat\n\nsee [above](#chatt)\n")

    (link,) = extract_links(page)

    assert link["anchor"] == "chatt"
    assert link["anchor"] not in heading_slugs(page)


def test_the_docs_still_contain_the_links_these_checks_claim_to_cover():
    """A change to extraction that finds nothing would pass every check above."""
    assert len(_PAGE_LINKS) > 200
    assert len(_ANCHOR_LINKS) > 10
    assert len(nav_pages()) > 100


def test_docs_json_is_the_file_the_navigation_checks_read():
    assert json.loads(DOCS_JSON.read_text(encoding="utf-8"))["navigation"]
