import json
import os
import re
import tomllib
from pathlib import Path

import pytest
import yaml

from tests.helpers.edenai_inventory import get_model_inventory
from tests.helpers.model_names import (
    BACKTICKED_MODEL_RE,
    DOCUMENTATION_PLACEHOLDERS,
    strip_tool_alias,
)
from tests.snippet_extractor import SKIP_COMMENT_RE

CONFIG_GUIDES = [
    "v3/integrations/bifrost.mdx",
    "v3/integrations/claude-code.mdx",
    "v3/integrations/cline.mdx",
    "v3/integrations/codex-cli.mdx",
    "v3/integrations/continue-dev.mdx",
    "v3/integrations/hermes.mdx",
    "v3/integrations/librechat.mdx",
    "v3/integrations/n8n.mdx",
    "v3/integrations/open-code-review.mdx",
    "v3/integrations/open-webui.mdx",
    "v3/integrations/openclaw.mdx",
    "v3/integrations/opencode.mdx",
    "v3/integrations/pi.mdx",
]

DOCS_ROOT = Path(__file__).resolve().parent.parent

ALLOWED_EDEN_HOSTS = {
    "api.edenai.run",
    "app.edenai.run",
    "docs.edenai.co",
    "app-edenai.instatus.com",
}

KNOWN_API_ENDPOINT_PREFIXES = ("/v2", "/v3")

FENCED_BLOCK_RE = re.compile(
    r"^```(?P<lang>[a-zA-Z]+)(?:[ \t]+[^\n]*)?[ \t]*\n(?P<body>.*?)^\s*```",
    re.MULTILINE | re.DOTALL,
)

EDEN_URL_RE = re.compile(
    r"https://(?P<host>[a-z0-9][a-z0-9\-]*(?:\.[a-z0-9\-]+)+)(?P<path>/[^\s'\"`)>]*)?"
)

CONFIG_PARSERS = {
    "json": json.loads,
    "yaml": yaml.safe_load,
    "yml": yaml.safe_load,
    "toml": tomllib.loads,
}


def parse_fenced_config_blocks(content: str) -> list[dict]:
    blocks = []
    for m in FENCED_BLOCK_RE.finditer(content):
        lang = m.group("lang").lower()
        if lang not in CONFIG_PARSERS:
            continue
        preceding = content[: m.start()]
        recent_lines = preceding.rsplit("\n", 3)[-3:]
        if any(SKIP_COMMENT_RE.search(line) for line in recent_lines):
            continue
        blocks.append(
            {
                "lang": lang,
                "body": m.group("body"),
                "line": preceding.count("\n") + 1,
            }
        )
    return blocks


def find_eden_urls(content: str) -> list[dict]:
    urls = []
    for m in EDEN_URL_RE.finditer(content):
        urls.append(
            {
                "url": m.group(0),
                "host": m.group("host"),
                "path": (m.group("path") or "").split("?")[0].split("#")[0].rstrip("/"),
                "line": content[: m.start()].count("\n") + 1,
            }
        )
    return urls


def find_provider_model_strings(content: str) -> list[str]:
    return [
        f"{m.group('provider')}/{m.group('rest')}"
        for m in BACKTICKED_MODEL_RE.finditer(content)
    ]


@pytest.mark.parametrize("guide", CONFIG_GUIDES, ids=lambda p: Path(p).stem)
def test_config_guide(guide: str) -> None:
    if not os.environ.get("EDEN_AI_SANDBOX_API_TOKEN"):
        pytest.skip("EDEN_AI_SANDBOX_API_TOKEN not set")

    path = DOCS_ROOT / guide
    assert path.exists(), f"Guide not found: {path}"
    content = path.read_text(encoding="utf-8")
    inventory = get_model_inventory()
    errors: list[str] = []

    for block in parse_fenced_config_blocks(content):
        parser = CONFIG_PARSERS[block["lang"]]
        try:
            parser(block["body"])
        except Exception as exc:
            errors.append(
                f"line {block['line']}: {block['lang']} config block failed to parse: {exc}"
            )

    for u in find_eden_urls(content):
        if "edenai" not in u["host"] and "instatus" not in u["host"]:
            continue
        if u["host"] not in ALLOWED_EDEN_HOSTS:
            errors.append(
                f"line {u['line']}: unexpected Eden AI host `{u['host']}` in {u['url']}"
            )
            continue
        if u["host"] == "api.edenai.run" and u["path"]:
            if not any(u["path"].startswith(prefix) for prefix in KNOWN_API_ENDPOINT_PREFIXES):
                errors.append(
                    f"line {u['line']}: unknown API endpoint path `{u['path']}` in {u['url']}"
                )

    for pm in find_provider_model_strings(content):
        if pm in DOCUMENTATION_PLACEHOLDERS:
            continue
        if pm in inventory or strip_tool_alias(pm) in inventory:
            continue
        errors.append(f"unknown model `{pm}` (not in live inventory)")

    if errors:
        pytest.fail(f"{guide}:\n  " + "\n  ".join(errors))
