"""Load .mdx documentation files as retrieval context for deepeval."""

from __future__ import annotations

import re
from pathlib import Path

# Matches YAML frontmatter block at the start of an MDX file
_FRONTMATTER_RE = re.compile(r"\A---\s*\n.*?\n---\s*\n", re.DOTALL)
# tests/evals/ -> tests/ -> repo root
_DOCS_ROOT = Path(__file__).resolve().parent.parent.parent


def load_doc_context(
    source_doc: str | list[str],
    docs_root: Path | None = None,
) -> list[str]:
    """Read one or more .mdx files and return their content as retrieval context.

    Args:
        source_doc: Relative path(s) to .mdx file(s), e.g. "v3/llms/chat-completions.mdx"
            or ["v3/llms/chat-completions.mdx", "v3/general/caching.mdx"].
        docs_root: Root directory of the docs repo. Defaults to the repo root.

    Returns:
        List of strings, one per source doc — the format deepeval expects
        for ``retrieval_context``.
    """
    if docs_root is None:
        docs_root = _DOCS_ROOT

    if isinstance(source_doc, str):
        source_doc = [source_doc]

    contexts: list[str] = []
    for path in source_doc:
        full_path = docs_root / path
        raw = full_path.read_text(encoding="utf-8")
        text = _strip_frontmatter(raw)
        contexts.append(text)

    return contexts


def _strip_frontmatter(text: str) -> str:
    """Remove YAML frontmatter from the beginning of an MDX file."""
    return _FRONTMATTER_RE.sub("", text)
