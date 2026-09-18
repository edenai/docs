"""Unit tests for the block extractor itself.

These never touch the network or the real docs tree: each one writes a small
.mdx file and asserts on what comes back, so a change to the fence or marker
rules fails here rather than silently changing which snippets get tested.
"""

from tests.snippet_extractor import extract_python_blocks


def write_page(tmp_path, body: str):
    page = tmp_path / "page.mdx"
    page.write_text(body, encoding="utf-8")
    return page


def test_marker_above_a_codegroup_covers_a_later_fence_in_it(tmp_path):
    """A group is marked as a whole, so the marker cannot be first-tab only."""
    page = write_page(
        tmp_path,
        "{/* skip-test: the whole group is illustrative */}\n"
        "<CodeGroup>\n"
        "```javascript JavaScript\n"
        "console.log(1);\n"
        "```\n"
        "```python Python\n"
        "print(1)\n"
        "```\n"
        "</CodeGroup>\n",
    )

    blocks = extract_python_blocks(page)

    assert len(blocks) == 1
    assert blocks[0]["skip"] is True
    assert blocks[0]["skip_reason"] == "the whole group is illustrative"
