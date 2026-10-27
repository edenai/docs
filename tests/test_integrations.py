"""Checks that the program an integration page configures can talk to Eden AI.

test_config_blocks.py checks the file a reader pastes: it parses, and the
names in it exist. That leaves the request the program then sends unchecked,
and it is a different request on nearly every page. Claude Code speaks the
Anthropic Messages API and authenticates with x-api-key, Codex speaks the
Responses API, and every coding agent attaches its tool definitions to every
request. A page can pass every config check and still point its tool at a
model that cannot take tools, or at a route that does not speak its protocol.

What runs where, cheapest first:

  - Every pull request, no credentials: every model the page names anywhere
    is one Eden AI serves, every setting that holds a model names one in full,
    and an agent is only pointed at models whose catalog entry says they take
    tools.
  - Every pull request, sandbox token: for each page, the request its tool
    sends, with the page's lead model and the auth the tool uses. The sandbox
    answers with a canned completion, so this proves the request is served,
    and costs nothing.
  - Weekly, production token: every model the pages name, sent through the
    protocol of every tool naming it, and for an agent the whole tool loop,
    with a real model that has to call the tool and answer with its result.

The real CLIs, for the tools that have one a test can run headless, are in
test_integration_clis.py.
"""

import anthropic
import openai
import pytest

from tests.config_blocks import (
    catalog_ids,
    catalog_routes,
    config_pages,
    normalize_model_id,
)
from tests.helpers.api import api_base_url
from tests.helpers.protocols import send
from tests.helpers.script_snippets import require_token
from tests.integrations import (
    TOOLS,
    Tool,
    chat_models,
    mentions,
    model_settings,
    paid_replays,
    registered_pages,
    request_for,
    sandbox_replays,
    source,
)

_PAGES = registered_pages()

_MENTION_CASES = [
    (page, mention)
    for page in _PAGES
    for mention in mentions(page)
    # A model inside a config block is checked by test_config_blocks.py, with
    # the block it sits in.
    if not mention.in_config_block
]
_SETTING_CASES = [
    (page, setting) for page in _PAGES for setting in model_settings(page)
]
_AGENT_MODEL_CASES = [
    (page, model)
    for page in _PAGES
    if TOOLS[page.stem].sends_tools
    for model in chat_models(page)
]
_SANDBOX_REPLAYS = sandbox_replays()
_PAID_REPLAYS = paid_replays()


def _mention_id(case) -> str:
    page, mention = case
    return f"{source(page)}::{mention.line}::{mention.model}"


def _setting_id(case) -> str:
    page, setting = case
    return f"{source(page)}::{setting.line}::{setting.key}"


def _agent_model_id(case) -> str:
    page, model = case
    return f"{source(page)}::{model}"


def _replay_id(replay) -> str:
    return f"{replay.pages[0]}::{replay.request}::{replay.model}"


def _paid_replay_id(replay) -> str:
    tools = "+tools" if replay.tools else ""
    return f"{replay.request}{tools}::{replay.model}"


def _replay(replay, token: str, round_trip: bool) -> None:
    """Send the request and turn a refusal into a failure a reader can act on."""
    base_url = f"{api_base_url()}/v3"
    where = ", ".join(replay.pages)
    what = f"{replay.request} request{' with tools' if replay.tools else ''}"
    try:
        send(
            replay.request,
            base_url,
            token,
            replay.model,
            tools=replay.tools,
            round_trip=round_trip,
        )
    except (openai.APIStatusError, anthropic.APIStatusError) as error:
        pytest.fail(
            f"{where}: a {what} for '{replay.model}' to {base_url} was refused "
            f"with {error.status_code}.\n  {error.message}"
        )
    except (openai.APIConnectionError, anthropic.APIConnectionError) as error:
        pytest.fail(f"{where}: a {what} to {base_url} never got an answer: {error}")
    except (openai.OpenAIError, anthropic.AnthropicError, AssertionError) as error:
        # The SDK's own complaints about a response it received, such as a
        # stream that ended on a content filter, mean the same as ours.
        pytest.fail(
            f"{where}: a {what} for '{replay.model}' was answered, but not in a "
            f"shape the tool can use: {error}"
        )


# --- reading a page --------------------------------------------------------


def _page(tmp_path, text: str):
    page = tmp_path / "page.mdx"
    page.write_text(text)
    return page


def test_a_key_called_model_is_a_model_setting(tmp_path):
    page = _page(tmp_path, '```json\n{"model": "openai/gpt-4"}\n```\n')

    assert [(s.key, s.value) for s in model_settings(page)] == [
        ("model", "openai/gpt-4")
    ]


def test_a_variable_ending_in_model_is_a_model_setting(tmp_path):
    """RAG_EMBEDDING_MODEL and AUDIO_STT_MODEL are where bare names hide."""
    page = _page(tmp_path, "```bash .env\nAUDIO_STT_MODEL=whisper-1\n```\n")

    assert [(s.key, s.value) for s in model_settings(page)] == [
        ("AUDIO_STT_MODEL", "whisper-1")
    ]


def test_a_command_line_model_flag_is_a_model_setting(tmp_path):
    page = _page(tmp_path, "```bash\nrepowise init --model mistral/x\n```\n")

    assert [s.value for s in model_settings(page)] == ["mistral/x"]


def test_a_key_that_only_starts_with_model_is_not_a_setting(tmp_path):
    page = _page(
        tmp_path,
        '```toml\nmodel_reasoning_effort = "high"\n```\n'
        "```yaml\nmodel_providers:\n  - name: x\n```\n",
    )

    assert model_settings(page) == ()


def test_a_wildcard_or_a_variable_is_not_a_model_setting(tmp_path):
    page = _page(
        tmp_path,
        "```yaml\nmodel: edenai/*\ndefault_model: ${MODEL}\n```\n"
        '```json\n{"tabAutocompleteModel": {}}\n```\n',
    )

    assert model_settings(page) == ()


def test_python_code_is_not_read_for_settings(tmp_path):
    """`model=model_id` is code, and the Python blocks run anyway."""
    page = _page(tmp_path, "```python\nclient.create(model=model_id)\n```\n")

    assert model_settings(page) == ()


def test_a_model_in_prose_is_a_mention(tmp_path):
    page = _page(tmp_path, "Pick `openai/text-embedding-3-small` for search.\n")

    assert [(m.model, m.line) for m in mentions(page)] == [
        ("openai/text-embedding-3-small", 1)
    ]


def test_a_mention_knows_whether_it_is_in_a_config_block(tmp_path):
    page = _page(
        tmp_path,
        '```json\n{"model": "openai/gpt-4"}\n```\n\nOr use `mistral/x`.\n',
    )

    assert [(m.model, m.in_config_block) for m in mentions(page)] == [
        ("openai/gpt-4", True),
        ("mistral/x", False),
    ]


def test_an_sdk_import_path_is_not_a_mention(tmp_path):
    page = _page(
        tmp_path,
        "```ts\nimport type { X } from 'openai/resources/chat/completions';\n```\n",
    )

    assert mentions(page) == ()


def test_a_chat_model_takes_the_protocol_of_the_tool():
    model = "anthropic/claude-sonnet-latest"

    for protocol in ("chat", "messages", "responses"):
        assert request_for(model, Tool(protocol)) == protocol


def test_an_embeddings_model_takes_an_embeddings_call_whatever_the_tool():
    assert (
        request_for("openai/text-embedding-3-small", Tool("messages")) == "embeddings"
    )


def test_a_request_two_pages_send_is_sent_once_and_names_both():
    seen = [(r.request, r.model, r.tools) for r in _PAID_REPLAYS]

    assert len(seen) == len(set(seen))
    assert any(len(r.pages) > 1 for r in _PAID_REPLAYS)


# --- the registry ----------------------------------------------------------


def test_every_integration_page_says_what_its_tool_speaks():
    pages = {page.stem for page in config_pages()}

    missing = sorted(pages - TOOLS.keys())
    assert not missing, (
        f"No entry in TOOLS (tests/integrations.py) for {missing}. Add one "
        f"saying which protocol the tool speaks, and whether it sends tool "
        f"definitions, so the request it makes is the one tested."
    )
    stale = sorted(TOOLS.keys() - pages)
    assert not stale, f"TOOLS names pages that no longer exist: {stale}"


# --- what a page names -----------------------------------------------------


@pytest.mark.parametrize("case", _MENTION_CASES, ids=_mention_id)
def test_a_model_named_on_an_integration_page_is_one_eden_ai_serves(case):
    page, mention = case

    assert normalize_model_id(mention.model) in catalog_ids(), (
        f"{source(page)} line {mention.line}: '{mention.model}' is not a model "
        f"Eden AI serves. A reader who picks it gets 'Model(s) not found' on "
        f"their first request."
    )


@pytest.mark.parametrize("case", _SETTING_CASES, ids=_setting_id)
def test_a_model_setting_names_a_whole_model_id(case):
    page, setting = case

    assert normalize_model_id(setting.value) in catalog_ids(), (
        f"{source(page)} line {setting.line}: {setting.key} is set to "
        f"'{setting.value}', which is not a model Eden AI serves. The tool "
        f"sends the value as it stands, so it needs the full provider/model id "
        f"from the catalog."
    )


@pytest.mark.parametrize("case", _AGENT_MODEL_CASES, ids=_agent_model_id)
def test_an_agent_is_only_pointed_at_models_that_take_tools(case):
    page, model = case
    capabilities = catalog_routes()["models"][model].get("capabilities") or {}

    assert capabilities.get("supports_function_calling"), (
        f"{source(page)}: the tool this page configures sends tool definitions "
        f"with every request, and the catalog says '{model}' does not support "
        f"function calling, so the first message fails."
    )


# --- what the tool sends ---------------------------------------------------


@pytest.mark.execute
@pytest.mark.parametrize("replay", _SANDBOX_REPLAYS, ids=_replay_id)
def test_the_request_a_tool_sends_is_served(replay):
    _replay(replay, require_token(paid=False), round_trip=False)


@pytest.mark.execute
@pytest.mark.parametrize("replay", _PAID_REPLAYS, ids=_paid_replay_id)
def test_a_model_a_page_names_works_through_the_tool_it_names_it_for(replay):
    _replay(replay, require_token(paid=True), round_trip=True)


# --- the checks have something to check ------------------------------------


def test_the_checks_still_find_what_they_claim_to_cover():
    """A scanning change that quietly found nothing would pass everything."""
    assert len(_PAGES) > 25, f"only {len(_PAGES)} integration pages registered"
    assert len(_MENTION_CASES) > 50, f"only {len(_MENTION_CASES)} mentions"
    assert len(_SETTING_CASES) > 50, f"only {len(_SETTING_CASES)} model settings"
    assert len(_AGENT_MODEL_CASES) > 20, f"only {len(_AGENT_MODEL_CASES)} agent models"
    assert {r.request for r in _SANDBOX_REPLAYS} >= {
        "chat",
        "messages",
        "responses",
        "embeddings",
    }
    assert len(_SANDBOX_REPLAYS) >= len(_PAGES)
