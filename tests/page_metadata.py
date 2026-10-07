"""The title and description a page declares, and the copy its structured data keeps.

Mintlify reads a page's `title` and `description` from its frontmatter. The
title is the page heading and, with " - Eden AI Documentation" after it, the
title of the search result; the description is the snippet under it. Nearly
every page then repeats both as props of <TechArticleSchema>, which adds a
structured-data block of its own beside the one Mintlify builds from the
frontmatter. Two copies of one value drift apart unless something compares them, so this
reads both.
"""

import json
import re
from pathlib import Path

import yaml

_FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n", re.S)
_SCHEMA_RE = re.compile(r"<TechArticleSchema\b(.*?)/>", re.S)
# A prop is written one of three ways: a JS string, a template literal (which
# is what scripts/generate_features.py writes) or a plain attribute.
_PROP_RE = re.compile(
    r'^\s*(?P<name>\w+)=(?:\{(?P<js>".*")\}|\{`(?P<template>.*)`\}|"(?P<attr>[^"]*)")\s*$',
    re.M,
)
_TEMPLATE_ESCAPE_RE = re.compile(r"\\([\\`$])")


def frontmatter(page: Path) -> dict:
    """The page's frontmatter, or an empty dict if it has none."""
    match = _FRONTMATTER_RE.match(page.read_text(encoding="utf-8"))
    return (yaml.safe_load(match.group(1)) or {}) if match else {}


def schema_props(page: Path) -> dict[str, str] | None:
    """The string props of the page's <TechArticleSchema>, or None if it has none."""
    match = _SCHEMA_RE.search(page.read_text(encoding="utf-8"))
    if match is None:
        return None
    props = {}
    for prop in _PROP_RE.finditer(match.group(1)):
        if prop["js"] is not None:
            props[prop["name"]] = json.loads(prop["js"])
        elif prop["template"] is not None:
            props[prop["name"]] = _TEMPLATE_ESCAPE_RE.sub(r"\1", prop["template"])
        else:
            props[prop["name"]] = prop["attr"]
    return props
