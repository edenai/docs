"""What each integration page points its tool at, read off the page itself.

An integration page tells a reader to point some other program at Eden AI:
Claude Code, Codex, Continue, LibreChat. That program then sends Eden AI a
request the page never shows, in a protocol the page rarely names, so checking
the page's text says nothing about whether the program works. Claude Code
speaks the Anthropic Messages API, Codex the Responses API, nearly everything
else the chat completions API, and a coding agent attaches tool definitions to
every request it makes.

The one thing this module knows that the pages do not say is which of those a
tool sends, and that is TOOLS below: one line per page. Everything else comes
from the page, so a page that changes its model is tested on what it now says:

  - the models it names, anywhere: a config block, an export line, a table
    cell, a sentence telling the reader which one to pick;
  - the settings that hold a model, which have to name one in full, because a
    bare "whisper-1" is invisible to a scan that looks for provider/model.

Which request a model takes comes from the catalog rather than the page: an id
listed under embeddings/models answers an embeddings call, and a chat model
answers whatever protocol the page's tool speaks.
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from tests.config_blocks import (
    MODEL_CATALOG_ROUTES,
    catalog_ids,
    catalog_routes,
    config_pages,
    models_in,
    normalize_model_id,
)
from tests.helpers.api import api_base_url
from tests.snippet_extractor import (
    BASE_URL_RE,
    DOCS_ROOT,
    extract_config_blocks,
    extract_settings_blocks,
)

__all__ = [
    "TOOLS",
    "Mention",
    "Replay",
    "Setting",
    "Tool",
    "chat_models",
    "mentions",
    "model_settings",
    "paid_replays",
    "pointed_here",
    "registered_pages",
    "request_for",
    "sandbox_replays",
    "source",
    "unserved_here",
]


@dataclass(frozen=True)
class Tool:
    """How the program an integration page configures talks to Eden AI.

    `protocol` is the request it sends for a chat model: "chat" for chat
    completions, "messages" for the Anthropic Messages API, "responses" for
    the Responses API. `sends_tools` is for the agents: a coding agent
    attaches its tool definitions to every request, so a model that cannot
    take them fails on the first message, and the request a test sends has to
    carry them too.
    """

    protocol: str
    sends_tools: bool = False


# One entry per page under v3/integrations/, keyed by its file name. A new page
# fails test_every_integration_page_says_what_its_tool_speaks until it is
# added, which is the point: the protocol is the one fact the page cannot
# supply, and guessing it is how a page ends up tested on a request its tool
# never sends.
TOOLS: dict[str, Tool] = {
    # Frameworks and SDKs. Their own samples run in the snippet suites; this
    # adds the models their prose names.
    "aisuite": Tool("chat"),
    "any-llm": Tool("chat"),
    "atomic-agents": Tool("chat"),
    "haystack": Tool("chat"),
    "langchain": Tool("chat"),
    "openai-sdk-python": Tool("chat"),
    "openai-sdk-typescript": Tool("chat"),
    "pydantic-ai": Tool("chat"),
    "symfony": Tool("chat"),
    # Coding agents. Every request carries their tool definitions.
    "claude-code": Tool("messages", sends_tools=True),
    "codex-cli": Tool("responses", sends_tools=True),
    "cline": Tool("chat", sends_tools=True),
    "continue-dev": Tool("chat", sends_tools=True),
    "hermes": Tool("chat", sends_tools=True),
    "kilo-code": Tool("chat", sends_tools=True),
    "nanobot": Tool("chat", sends_tools=True),
    "openclaw": Tool("chat", sends_tools=True),
    "opencode": Tool("chat", sends_tools=True),
    "pi": Tool("chat", sends_tools=True),
    # Lynkr fronts Claude Code, Cursor and Codex, and calls Eden AI's chat
    # completions route itself, forwarding the tool definitions it receives.
    "lynkr": Tool("chat", sends_tools=True),
    # Chat interfaces, gateways and apps. Tools are optional in all of them.
    "bifrost": Tool("chat"),
    "deeptutor": Tool("chat"),
    "librechat": Tool("chat"),
    "n8n": Tool("chat"),
    "open-code-review": Tool("chat"),
    "open-connector": Tool("chat"),
    "open-webui": Tool("chat"),
    "plano": Tool("chat"),
    "py-gpt": Tool("chat"),
    "repowise": Tool("chat"),
}


# Which request a model takes, by the catalog route that lists it. A chat model,
# under "models", answers whatever the tool speaks, so it is not here. Every
# other route in MODEL_CATALOG_ROUTES is, so one added to the catalog fails
# loudly here rather than having its models silently left out of every run.
_ROUTE_REQUESTS = {
    "embeddings/models": "embeddings",
    "moderations/models": "moderations",
    "images/models": "images",
    "audio/transcriptions/models": "transcriptions",
    "audio/speech/models": "speech",
    # A video takes minutes to render and costs real money each time, so no
    # run sends one. No integration page names a video model today.
    "videos/models": None,
}
assert {"models", *_ROUTE_REQUESTS} == set(MODEL_CATALOG_ROUTES)

# KEY=value, "key": "value", key: value and key = "value", where the key ends
# in "model" or "models": model, titleModel, ANTHROPIC_DEFAULT_HAIKU_MODEL,
# DEFAULT_MODELS. A variable can also qualify the setting after the word, as
# TASK_MODEL_EXTERNAL does, though not before it: MODEL_PROVIDER names a
# provider. A key such as model_providers or modelDisplayLabel holds something
# else, so it never matches. A shell default, ${EDEN_MODEL:-openai/gpt-4o}, is
# read for the model it falls back to, and a value can be a comma-separated
# list.
_SETTING_RE = re.compile(
    r"(?<![\w.$-])(?<!\$\{)"
    r"(?P<key>(?:[A-Za-z_][\w.-]*?)?(?:(?i:models?)|_MODELS?_[A-Z][A-Z0-9_]*))"
    r"[\"']?\s*[=:]\s*[\"']?(?:\$\{\w+:?-)?(?P<value>[^\s\"'{}\[\]#]*)"
)
# Not -m as well: aider's -m is a message and python's is a module.
_FLAG_RE = re.compile(r"(?P<key>--model)[\s=]+[\"']?(?P<value>[^\s\"']+)")

# Values that name no model: a variable, a template, a wildcard, a switch, an
# empty JSON or YAML value.
_NOT_A_VALUE_RE = re.compile(
    r"^(?:$|[$%<]|.*\*|true$|false$|\d+$|null$|none$|~$)", re.IGNORECASE
)

# The text of a link out of the docs names what it links to, and a repository
# is named owner/name: [openai/codex](https://github.com/openai/codex). The URL
# never reads as a model, because its host comes first.
_EXTERNAL_LINK_RE = re.compile(r"\[[^\]]*\]\(https?://[^)]*\)")


@dataclass(frozen=True)
class Mention:
    """A model id written somewhere on a page."""

    model: str
    line: int
    in_config_block: bool


@dataclass(frozen=True)
class Setting:
    """A key or variable on a page whose value is a model."""

    key: str
    value: str
    line: int


@dataclass(frozen=True)
class Replay:
    """One request a tool sends: which call, which model, from which pages."""

    request: str
    model: str
    tools: bool
    pages: tuple[str, ...]


def source(page: Path) -> str:
    """The page as a reader of a failure would look for it."""
    return str(page.relative_to(DOCS_ROOT))


def pointed_here(text: str) -> str:
    """Text from a page, with its Eden AI host swapped for the one under test."""
    return BASE_URL_RE.sub(api_base_url(), text)


# Cached because a page is scanned by every check built from it, in every
# xdist worker, while collecting. A tuple, so no caller can change what the
# next one gets.
@cache
def mentions(page: Path) -> tuple[Mention, ...]:
    """Every model the page names, in order, each once at its first line.

    A mention inside a config block is marked as one, with the same extractor
    test_config_blocks.py walks, because that test reports it with its block.
    """
    config_lines = set()
    for block in extract_config_blocks(page):
        first = block["line"]
        config_lines.update(range(first, first + block["code"].count("\n") + 1))

    found: dict[str, Mention] = {}
    text = page.read_text(encoding="utf-8")
    for number, line in enumerate(text.splitlines(), start=1):
        for model in models_in(_EXTERNAL_LINK_RE.sub("", line)):
            found.setdefault(model, Mention(model, number, number in config_lines))
    return tuple(found.values())


@cache
def model_settings(page: Path) -> tuple[Setting, ...]:
    """Every setting on the page that holds a model, with what it holds."""
    settings = []
    for block in extract_settings_blocks(page):
        for offset, line in enumerate(block["code"].splitlines()):
            for match in (*_SETTING_RE.finditer(line), *_FLAG_RE.finditer(line)):
                for value in match.group("value").split(","):
                    if not _NOT_A_VALUE_RE.match(value):
                        settings.append(
                            Setting(match.group("key"), value, block["line"] + offset)
                        )
    return tuple(settings)


def request_for(model: str, tool: Tool) -> str | None:
    """The call this model answers when this tool sends it.

    None for a model no run sends a request to, which is a video model today.
    """
    bare = normalize_model_id(model)
    for route, entries in catalog_routes().items():
        if bare in entries:
            return tool.protocol if route == "models" else _ROUTE_REQUESTS[route]
    return None


def chat_models(page: Path) -> list[str]:
    """The chat models the page names, as Eden AI ids."""
    chat = catalog_routes()["models"]
    bare = (normalize_model_id(mention.model) for mention in mentions(page))
    return list(dict.fromkeys(model for model in bare if model in chat))


def unserved_here(models: Iterable[str]) -> list[str]:
    """The models, of these, that the API under test does not serve.

    A page is checked against production's catalog, because that is what a
    reader uses. A run pointed elsewhere, staging by default, can lack a model
    production has, and a request for it fails for a reason that has nothing
    to do with the page.
    """
    routes = catalog_routes(f"{api_base_url()}/v3")
    served = {model_id for entries in routes.values() for model_id in entries}
    return [model for model in models if normalize_model_id(model) not in served]


def registered_pages() -> list[Path]:
    """The integration pages TOOLS has an entry for.

    A page without one is reported by the test that checks TOOLS against the
    pages, by name. Raising a KeyError here instead would abort collection of
    every test in the module and name nothing.
    """
    return [page for page in config_pages() if page.stem in TOOLS]


def _requests(page: Path, tool: Tool) -> list[tuple[str, str, bool]]:
    """(request, model, tools) for every model on the page that a run can call.

    Tool definitions go with the tool's own protocol only: an agent attaches
    them to its chat requests, not to the embeddings call it makes to search.
    """
    served = catalog_ids()
    calls = []
    for mention in mentions(page):
        model = normalize_model_id(mention.model)
        if model not in served:
            # Reported by the catalog check, with the line it is on.
            continue
        request = request_for(model, tool)
        if request:
            calls.append(
                (request, model, tool.sends_tools and request == tool.protocol)
            )
    return calls


def sandbox_replays() -> list[Replay]:
    """One request per page and per kind of call, with the model it leads with.

    The sandbox answers every model with the same canned completion, so a
    second model on the same protocol tells it nothing new. What it can tell
    is whether the request the tool sends, with the auth the tool uses, is one
    Eden AI serves.
    """
    replays = []
    for page in registered_pages():
        firsts: dict[str, tuple[str, bool]] = {}
        for request, model, tools in _requests(page, TOOLS[page.stem]):
            firsts.setdefault(request, (model, tools))
        replays += [
            Replay(request, model, tools, (source(page),))
            for request, (model, tools) in firsts.items()
        ]
    return replays


def paid_replays() -> list[Replay]:
    """Every model the pages name, on the protocol of every tool naming it.

    A real model is where a page goes wrong in ways the sandbox cannot show: a
    Codex model the chat route refuses, a tool call that comes back in a shape
    the protocol does not allow. The same request sent for two pages is sent
    once, and its failure names both.
    """
    pages_for: dict[tuple[str, str, bool], list[str]] = {}
    for page in registered_pages():
        for call in _requests(page, TOOLS[page.stem]):
            pages = pages_for.setdefault(call, [])
            if source(page) not in pages:
                pages.append(source(page))
    return [
        Replay(request, model, tools, tuple(pages))
        for (request, model, tools), pages in sorted(pages_for.items())
    ]
