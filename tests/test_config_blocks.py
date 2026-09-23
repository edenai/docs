"""Checks the configuration a reader pastes into another tool's config file.

The integration pages tell a reader to point some other program at Eden AI:
Continue, Kilo Code, LibreChat, Codex CLI, OpenCode. What they paste is a
JSON, YAML or TOML file, and none of it was checked by anything. A snippet
runner cannot help here, because there is no program to run: the block is data
that a third-party tool reads, so the only things that can be wrong with it
are its syntax and the names inside it.

Three things can be wrong, and each is a check below:

  - It does not parse, so pasting it breaks the tool that reads it.
  - It names a model Eden AI does not serve, so the first request fails.
  - It points at an Eden AI URL that does not exist.

The model catalog is checked on every pull request rather than weekly, unlike
the third-party links in test_links_external.py. That split is about whose
site has to be up: weekly is for somebody else's, and this is Eden AI's own
public API. A model id going stale is worth catching on the pull request that
introduces it.

Not every block is a whole file. A page may show a menu of alternative values
for one key, or a single line of a larger document, and neither parses as
anything. Those carry the same {/* skip-test: reason */} marker every other
runner in this suite honours, so there is one mechanism rather than two. The
names inside them are still checked, because a menu of models goes stale like
any other.
"""

import pytest

from tests.config_blocks import (
    CONFIG_LANGUAGES,
    MODEL_CATALOG_ROUTES,
    catalog_ids,
    catalog_providers,
    config_blocks,
    config_pages,
    eden_urls,
    model_candidates,
    model_references,
    normalize_model_id,
    parse_config,
    url_exists,
    url_probe,
)
from tests.snippet_extractor import DOCS_ROOT, extract_config_blocks

_BLOCKS = config_blocks()
_PARSEABLE = [block for block in _BLOCKS if not block["skip"]]
_MODEL_CASES = [
    (block, model_id)
    for block in _BLOCKS
    for model_id in sorted(model_references(block))
]
_URL_CASES = [(block, url) for block in _BLOCKS for url in sorted(eden_urls(block))]


def _where(block: dict) -> str:
    return f"{block['source_mdx']} line {block['line']}"


def _block_id(block: dict) -> str:
    return f"{block['source_mdx']}::{block['line']}"


def _case_id(case: tuple) -> str:
    block, value = case
    return f"{_block_id(block)}::{value}"


# --- what counts as a config block -----------------------------------------


def test_a_json_fence_is_a_config_block(tmp_path):
    page = tmp_path / "page.mdx"
    page.write_text('Text.\n\n```json\n{"a": 1}\n```\n')

    blocks = extract_config_blocks(page)

    assert len(blocks) == 1
    assert blocks[0]["lang"] == "json"
    assert blocks[0]["code"].strip() == '{"a": 1}'


def test_a_yaml_and_a_toml_fence_are_config_blocks(tmp_path):
    page = tmp_path / "page.mdx"
    page.write_text("```yaml\na: 1\n```\n\n```toml\na = 1\n```\n")

    langs = [block["lang"] for block in extract_config_blocks(page)]

    assert langs == ["yaml", "toml"]


def test_an_nginx_fence_is_not_a_config_block(tmp_path):
    """No parser reads it and it names no models, so it is out of scope."""
    page = tmp_path / "page.mdx"
    page.write_text("```nginx\nserver { listen 443; }\n```\n")

    assert extract_config_blocks(page) == []


def test_a_config_block_knows_the_line_its_fence_is_on(tmp_path):
    page = tmp_path / "page.mdx"
    page.write_text("One\nTwo\nThree\n\n```json\n{}\n```\n")

    assert extract_config_blocks(page)[0]["line"] == 6


def test_a_marked_block_carries_its_reason(tmp_path):
    page = tmp_path / "page.mdx"
    page.write_text(
        '{/* skip-test: one key of a larger file */}\n```json\n"a": 1\n```\n'
    )

    block = extract_config_blocks(page)[0]

    assert block["skip"] is True
    assert block["skip_reason"] == "one key of a larger file"


def test_a_marker_above_a_codegroup_covers_every_tab(tmp_path):
    """A menu is written as a group, so the marker has to reach every tab."""
    page = tmp_path / "page.mdx"
    page.write_text(
        "{/* skip-test: alternatives, not a file */}\n"
        "<CodeGroup>\n"
        '```toml A\nmodel = "x"\n```\n\n'
        '```toml B\nmodel = "y"\n```\n'
        "</CodeGroup>\n"
    )

    assert [block["skip"] for block in extract_config_blocks(page)] == [True, True]


# --- parsing ---------------------------------------------------------------


def test_valid_json_parses():
    assert parse_config("json", '{"a": 1}') == {"a": 1}


def test_valid_yaml_parses():
    assert parse_config("yaml", "a: 1") == {"a": 1}


def test_valid_toml_parses():
    assert parse_config("toml", 'a = "1"') == {"a": "1"}


def test_broken_json_raises():
    with pytest.raises(Exception):
        parse_config("json", '{"a": }')


def test_a_toml_file_repeating_a_key_raises():
    """The menu form: one key given several alternative values."""
    with pytest.raises(Exception):
        parse_config("toml", 'model = "a"\nmodel = "b"')


# --- what counts as a model id ---------------------------------------------


def test_a_model_id_is_found_under_a_json_key():
    block = {"code": '{"model": "openai/gpt-4"}'}

    assert model_candidates(block) == {"openai/gpt-4"}


def test_a_model_id_is_found_in_a_yaml_list_item():
    """LibreChat lists its models rather than assigning them to a key."""
    block = {"code": 'models:\n  default:\n    - "anthropic/claude-sonnet-latest"\n'}

    assert model_candidates(block) == {"anthropic/claude-sonnet-latest"}


def test_a_model_id_is_found_in_a_compose_environment_entry():
    block = {"code": "  - RAG_EMBEDDING_MODEL=openai/text-embedding-3-small\n"}

    assert model_candidates(block) == {"openai/text-embedding-3-small"}


def test_a_url_is_not_a_model_id():
    block = {"code": '{"apiBase": "https://api.edenai.run/v3"}'}

    assert model_candidates(block) == set()


def test_a_docker_image_tag_is_not_a_model_id():
    block = {"code": "image: ghcr.io/open-webui/open-webui:main\n"}

    assert model_candidates(block) == set()


def test_a_wildcard_is_not_a_model_id():
    block = {"code": '{"models": "edenai/*"}'}

    assert model_candidates(block) == set()


def test_a_mime_type_survives_the_shape_rule_and_fails_the_provider_rule():
    """Why the provider rule exists: "image/gif" is the right shape."""
    block = {"code": '{"supportedMimeTypes": ["image/gif"]}'}

    assert model_candidates(block) == {"image/gif"}
    assert model_references(block) == set()


def test_a_tool_prefix_is_stripped_from_a_model_id():
    assert (
        normalize_model_id("edenai/anthropic/claude-sonnet-5")
        == "anthropic/claude-sonnet-5"
    )


def test_a_plain_model_id_is_left_alone():
    assert (
        normalize_model_id("anthropic/claude-sonnet-5") == "anthropic/claude-sonnet-5"
    )


def test_an_id_with_several_slashes_keeps_all_but_the_tool_prefix():
    assert (
        normalize_model_id("edenai/together_ai/meta-models/Muse-Glimmer-30B")
        == "together_ai/meta-models/Muse-Glimmer-30B"
    )


# --- eden urls -------------------------------------------------------------


def test_an_eden_url_is_found_in_a_block():
    block = {"code": '{"apiBase": "https://api.edenai.run/v3"}'}

    assert eden_urls(block) == {"https://api.edenai.run/v3"}


def test_the_european_host_is_an_eden_url():
    block = {"code": '{"apiBase": "https://api.eu.edenai.run/v3"}'}

    assert eden_urls(block) == {"https://api.eu.edenai.run/v3"}


def test_another_hosts_url_is_not_an_eden_url():
    block = {"code": "base: http://localhost:3000\n"}

    assert eden_urls(block) == set()


def test_a_base_url_is_judged_by_what_sits_under_it():
    """On its own it is a 404 forever, because the tool appends the path."""
    assert url_probe("https://api.edenai.run/v3") == "https://api.edenai.run/v3/models"


def test_an_endpoint_url_is_requested_as_written():
    url = "https://api.edenai.run/v3/chat/completions"

    assert url_probe(url) == url


# --- the catalog -----------------------------------------------------------


def test_the_catalog_covers_more_than_the_chat_models():
    """/v3/models is chat only, so an embeddings model is the proof."""
    assert "openai/text-embedding-3-small" in catalog_ids()


def test_the_catalog_names_providers_and_not_mime_types():
    providers = catalog_providers()

    assert "openai" in providers
    assert "image" not in providers


# --- the docs themselves ---------------------------------------------------


@pytest.mark.parametrize("block", _PARSEABLE, ids=_block_id)
def test_a_config_block_parses_as_the_language_it_declares(block):
    try:
        parse_config(block["lang"], block["code"])
    except Exception as error:
        pytest.fail(
            f"{_where(block)}: this {block['lang']} block does not parse, so "
            f"pasting it breaks the file it goes in.\n"
            f"  {type(error).__name__}: {error}\n"
            f"If it is a fragment or a menu of alternatives rather than a "
            f"whole file, mark it {{/* skip-test: why */}}."
        )


@pytest.mark.parametrize("case", _MODEL_CASES, ids=_case_id)
def test_a_model_named_in_a_config_block_is_one_eden_ai_serves(case):
    block, model_id = case
    bare = normalize_model_id(model_id)

    assert bare in catalog_ids(), (
        f"{_where(block)}: '{model_id}' is not a model Eden AI serves, so the "
        f"first request this configuration makes fails. The catalog is the "
        f"union of {len(MODEL_CATALOG_ROUTES)} routes; /v3/models alone is "
        f"chat only."
    )


@pytest.mark.parametrize("case", _URL_CASES, ids=_case_id)
def test_a_url_in_a_config_block_points_at_something(case):
    block, url = case
    probe = url_probe(url)
    where = url if probe == url else f"{url} (checked as {probe})"

    assert url_exists(probe), f"{_where(block)}: {where} does not answer."


# --- the checks have something to check ------------------------------------


def test_the_docs_still_contain_the_blocks_these_checks_claim_to_cover():
    """An extraction change that quietly found nothing would pass everything."""
    assert len(_BLOCKS) > 40, f"only {len(_BLOCKS)} config blocks found"
    assert len(_MODEL_CASES) > 20, f"only {len(_MODEL_CASES)} model references found"
    assert len(_URL_CASES) > 10, f"only {len(_URL_CASES)} Eden AI URLs found"


def test_every_config_block_comes_from_a_page_that_exists():
    for block in _BLOCKS:
        assert (DOCS_ROOT / block["source_mdx"]).is_file(), block["source_mdx"]


def test_the_pages_read_are_the_integration_pages():
    pages = config_pages()

    assert len(pages) > 25
    assert all(page.parent.name == "integrations" for page in pages)


def test_the_languages_checked_are_the_ones_the_docs_use():
    assert CONFIG_LANGUAGES == ("json", "yaml", "yml", "toml")
