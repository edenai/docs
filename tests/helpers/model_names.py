import re

BACKTICKED_MODEL_RE = re.compile(
    r"`(?P<provider>[a-z][a-z0-9\-]{1,30})/(?P<rest>[A-Za-z0-9][A-Za-z0-9\-_.:/]{0,120}?)`"
)

DOCUMENTATION_PLACEHOLDERS = frozenset(
    {
        "provider/model",
        "feature/subfeature",
        "feature/subfeature/provider",
        "feature/subfeature/provider/model",
        "your/model",
        "your/provider",
    }
)

UNAMBIGUOUS_MIME_PREFIXES = frozenset(
    {"application", "multipart", "font", "message", "example"}
)

TOOL_ALIAS_PREFIXES = frozenset({"edenai"})


def strip_tool_alias(candidate: str) -> str:
    head, sep, rest = candidate.partition("/")
    if sep and head in TOOL_ALIAS_PREFIXES:
        return rest
    return candidate
