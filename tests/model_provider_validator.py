import os
from pathlib import Path

import pytest

from tests.helpers.edenai_inventory import get_model_inventory
from tests.helpers.model_names import (
    BACKTICKED_MODEL_RE,
    DOCUMENTATION_PLACEHOLDERS,
    UNAMBIGUOUS_MIME_PREFIXES,
    strip_tool_alias,
)

DOCS_ROOT = Path(__file__).resolve().parent.parent


def _pages() -> list[str]:
    return sorted(
        str(p.relative_to(DOCS_ROOT))
        for p in list(DOCS_ROOT.glob("v3/**/*.mdx")) + list(DOCS_ROOT.glob("*.mdx"))
        if not str(p.relative_to(DOCS_ROOT)).startswith("api-reference/")
    )


@pytest.mark.parametrize("page", _pages())
def test_model_and_provider_names(page: str) -> None:
    if not os.environ.get("EDEN_AI_SANDBOX_API_TOKEN"):
        pytest.skip("EDEN_AI_SANDBOX_API_TOKEN not set")

    inventory = get_model_inventory()
    known_prefixes = {entry.split("/", 1)[0] for entry in inventory}
    content = (DOCS_ROOT / page).read_text(encoding="utf-8")

    unknown: list[str] = []
    seen: set[str] = set()

    for match in BACKTICKED_MODEL_RE.finditer(content):
        provider_or_feature = match.group("provider")
        candidate = f"{provider_or_feature}/{match.group('rest')}"
        if candidate in seen:
            continue
        seen.add(candidate)

        if candidate in inventory or strip_tool_alias(candidate) in inventory:
            continue
        if candidate in DOCUMENTATION_PLACEHOLDERS:
            continue
        if provider_or_feature in UNAMBIGUOUS_MIME_PREFIXES:
            continue

        line = content[: match.start()].count("\n") + 1
        if provider_or_feature in known_prefixes:
            unknown.append(
                f"line {line}: unknown model `{candidate}` "
                f"(prefix `{provider_or_feature}` is known)"
            )
        else:
            unknown.append(
                f"line {line}: unknown model or provider `{candidate}`"
            )

    if unknown:
        pytest.fail(f"{page}:\n  " + "\n  ".join(unknown))
