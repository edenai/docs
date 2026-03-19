#!/usr/bin/env python3
"""
Generate Mintlify MDX documentation pages from the Eden AI /v3/info API.

Usage:
    python scripts/generate_features.py

No dependencies beyond Python stdlib are required.
"""

import json
import os
import re
import shutil
import tempfile
import urllib.request
from pathlib import Path

# --------------------------
# Configuration
# --------------------------
API_BASE = "https://api.edenai.run"
INFO_ENDPOINT = f"{API_BASE}/v3/info"

# Root of the Mintlify docs site (where docs.json lives)
DOCS_ROOT = Path(__file__).resolve().parent.parent
FEATURES_DIR = DOCS_ROOT / "v3" / "expert-models" / "features"
DOCS_JSON_PATH = DOCS_ROOT / "docs.json"

# Fallback icon when no keyword match is found
DEFAULT_FEATURE_ICON = "cube"
DEFAULT_SUBFEATURE_ICON = "microchip-ai"

# Keyword → icon mapping for auto-detecting a sensible icon per feature category
_ICON_KEYWORDS = {
    "text": "font",
    "ocr": "file-lines",
    "document": "file-lines",
    "image": "image",
    "video": "video",
    "translation": "language",
    "audio": "volume-high",
    "speech": "volume-high",
}

# ---------------------
# API helpers
# ---------------------


def fetch_json(url: str) -> dict:
    """Fetch JSON from a URL using only stdlib."""
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def fetch_all_features() -> list[dict]:
    data = fetch_json(INFO_ENDPOINT)
    return data.get("features", [])


def fetch_subfeature_detail(feature: str, subfeature: str) -> dict:
    url = f"{INFO_ENDPOINT}/{feature}/{subfeature}?format=simplified"
    return fetch_json(url)


# -------------------------------------------------------------
# Feature display name / icon derivation (fully automatic)
# -------------------------------------------------------------


# Words that should stay uppercase in display names
_UPPERCASE_WORDS = {"ocr", "ai", "api", "llm", "tts", "nlu", "nlp", "id"}


def _smart_title(text: str) -> str:
    """Title-case a string while preserving known acronyms."""
    words = text.replace("_", " ").split()
    return " ".join(w.upper() if w.lower() in _UPPERCASE_WORDS else w.title() for w in words)


def derive_display_name(feature: dict) -> str:
    """Derive a human-friendly display name for a top-level feature category.

    Strategy:
    1. If the API's fullname differs from the raw name, use it (smart-title-cased).
    2. Otherwise, find the longest common prefix among subfeature fullnames
       that is longer than the raw name alone (e.g. "Image Background removal",
       "Image Object Detection" → "Image").
    3. If the common prefix is just the raw feature name (single word),
       try to pick a descriptive suffix from the subfeatures' domain.
    4. Final fallback: smart-title-case the raw name.
    """
    raw = feature["name"]
    fullname = feature.get("fullname") or raw

    # If the API already provides a proper display name
    if fullname.lower() != raw.lower():
        return _smart_title(fullname)

    # Try to extract a common prefix from subfeature fullnames
    sf_names = [
        sf.get("fullname", "") for sf in feature.get("subfeatures", []) if sf.get("fullname")
    ]
    if sf_names:
        prefix = _common_word_prefix(sf_names)
        # If prefix is more descriptive than just the raw name, use it
        if prefix and len(prefix.split()) > 1:
            return _smart_title(prefix)

    # Fallback: smart-title-case the raw name
    return _smart_title(raw)


def _common_word_prefix(strings: list[str]) -> str:
    """Return the longest common word-level prefix of a list of strings."""
    if not strings:
        return ""
    words_list = [s.split() for s in strings]
    prefix_words = []
    for parts in zip(*words_list):
        if len(set(w.lower() for w in parts)) == 1:
            prefix_words.append(parts[0])
        else:
            break
    return " ".join(prefix_words)


def derive_icon(feature_name: str) -> str:
    """Pick an icon based on keyword matching against the feature name."""
    name_lower = feature_name.lower()
    for keyword, icon in _ICON_KEYWORDS.items():
        if keyword in name_lower:
            return icon
    return DEFAULT_FEATURE_ICON


# ----------------------
# Formatting helpers
# ----------------------


def escape_frontmatter(text: str) -> str:
    """Escape a string for use inside double-quoted YAML frontmatter."""
    return text.replace("\\", "\\\\").replace('"', '\\"')


def truncate_at_word(text: str, max_len: int) -> str:
    """Truncate text at a word boundary, appending '...' if shortened."""
    if len(text) <= max_len:
        return text
    truncated = text[:max_len].rsplit(" ", 1)[0]
    return truncated + "..."


_HTML_TAG_RE = re.compile(r"<[^>]+>")


def strip_html(text: str) -> str:
    """Remove HTML/JSX tags from text to prevent injection in MDX output."""
    return _HTML_TAG_RE.sub("", text)


def format_price(price: float, quantity: int, unit_type: str) -> str:
    """Return a human-readable price string."""
    if price == 0:
        return "Free"
    if quantity == 1:
        return f"${price:g} per {unit_type}"
    return f"${price:g} per {quantity:,} {unit_type}s"


def provider_from_model(model_str: str) -> str:
    """Extract provider name from a model string like 'text/moderation/openai/gpt-4o'."""
    parts = model_str.split("/")
    return parts[2] if len(parts) >= 3 else model_str


def model_label(model_str: str) -> str:
    """Extract a short model label (provider + optional model variant)."""
    parts = model_str.split("/")
    if len(parts) >= 4:
        return f"{parts[2]} ({'/'.join(parts[3:])})"
    return parts[2] if len(parts) >= 3 else model_str


def slug(name: str) -> str:
    """Convert a subfeature name to a URL-friendly slug."""
    return name.replace("_", "-")


# Realistic placeholder values keyed by (field_name, field_type).
# Checked in order: exact name match first, then type-based fallback.
_FIELD_PLACEHOLDERS: dict[str, str] = {
    # By field name
    "text": '"The quick brown fox jumps over the lazy dog."',
    "texts": '["First text to analyze", "Second text to analyze"]',
    "file": '"YOUR_FILE_UUID_OR_URL"',
    "file_url": '"https://example.com/document.pdf"',
    "language": '"en"',
    "source_language": '"en"',
    "target_language": '"fr"',
    "speakers": "2",
    "profanity_filter": "false",
    "vocabulary": '["Eden AI", "API"]',
    "resolution": '"1024x1024"',
    "num_images": "1",
    "text_prompt": '"A futuristic city skyline at sunset"',
    "document_type": '"auto-detect"',
}

_TYPE_PLACEHOLDERS: dict[str, str] = {
    "string": '"example"',
    "int": "1",
    "integer": "1",
    "float": "0.5",
    "number": "0.5",
    "bool": "true",
    "boolean": "true",
    "file_input": '"YOUR_FILE_UUID_OR_URL"',
}


def _placeholder_for_field(field: dict) -> str:
    """Return a realistic JSON placeholder value for a schema field."""
    name = field.get("name", "")
    ftype = field.get("type", "string")

    # Exact name match
    if name in _FIELD_PLACEHOLDERS:
        return _FIELD_PLACEHOLDERS[name]

    # Enum: use the first allowed value
    if ftype == "enum" and field.get("enum"):
        return f'"{field["enum"][0]}"'

    # Array of strings
    if ftype == "array":
        return '["value1", "value2"]'

    # Type-based fallback
    return _TYPE_PLACEHOLDERS.get(ftype, '"value"')


def build_input_json(fields: list[dict], required_only: bool = False) -> dict[str, str]:
    """Build a dict of field_name → placeholder value from schema fields.

    Includes all required fields plus optional fields that add useful context
    (like language). Returns an ordered dict suitable for JSON serialization.
    """
    # Always-include optional fields that improve the example
    useful_optional = {"language", "source_language", "target_language"}

    result: dict[str, str] = {}
    for f in fields:
        name = f.get("name", "")
        is_required = f.get("required", False)
        if is_required or (not required_only and name in useful_optional):
            result[name] = _placeholder_for_field(f)
    return result


# --------------------
# MDX generation
# --------------------

def _render_fields_rows(fields: list[dict], depth: int = 0) -> list[str]:
    """Recursively render schema fields as table rows, expanding nested objects."""
    rows = []
    indent = "&nbsp;&nbsp;&nbsp;&nbsp;" * depth  # visual indentation per nesting level
    for f in fields:
        name = f.get("name", "")
        ftype = f.get("type", "")
        required = "Yes" if f.get("required") else "No"
        desc = strip_html(f.get("description", ""))

        if ftype == "array" and "items" in f:
            item_type = f["items"].get("type", "")
            nested_fields = f["items"].get("fields", [])
            if item_type == "object" and nested_fields:
                rows.append(f"| {indent}**{name}** | array[object] | {required} | {desc} |")
                rows.extend(_render_fields_rows(nested_fields, depth=depth + 1))
            else:
                ftype = f"array[{item_type}]" if item_type else "array"
                rows.append(f"| {indent}{name} | {ftype} | {required} | {desc} |")
        elif ftype == "object" and "fields" in f:
            rows.append(f"| {indent}**{name}** | object | {required} | {desc} |")
            rows.extend(_render_fields_rows(f["fields"], depth=depth + 1))
        else:
            rows.append(f"| {indent}{name} | {ftype} | {required} | {desc} |")
    return rows


def render_schema_table(fields: list[dict], indent: int = 0) -> str:
    """Render a list of schema fields as a Markdown table, expanding nested objects."""
    if not fields:
        return "_No schema information available._\n"

    lines = [
        "| Field | Type | Required | Description |",
        "|-------|------|----------|-------------|",
    ]
    lines.extend(_render_fields_rows(fields))
    return "\n".join(lines) + "\n"


def render_providers_table(models: list[dict]) -> str:
    """Render available providers/models as a Markdown table."""
    if not models:
        return "_No providers currently available._\n"

    lines = [
        "| Provider | Model String | Price |",
        "|----------|-------------|-------|",
    ]
    for m in models:
        model_str = m.get("model", "")
        label = model_label(model_str)
        pricing = m.get("pricing", {})
        price_str = format_price(
            pricing.get("price", 0),
            pricing.get("price_unit_quantity", 1),
            pricing.get("price_unit_type", "request"),
        )
        lines.append(f"| {label} | `{model_str}` | {price_str} |")
    return "\n".join(lines) + "\n"


def _format_input_block(fields: list[dict], indent: int = 8) -> str:
    """Format the input fields as a JSON-like block for embedding in code."""
    input_map = build_input_json(fields)
    if not input_map:
        return "{}"
    pad = " " * indent
    lines = ["{"]
    items = list(input_map.items())
    for i, (k, v) in enumerate(items):
        comma = "," if i < len(items) - 1 else ""
        lines.append(f'{pad}"{k}": {v}{comma}')
    lines.append(" " * (indent - 4) + "}")
    return "\n".join(lines)


def _format_curl_input(fields: list[dict]) -> str:
    """Format the input fields as inline JSON for the cURL -d body."""
    input_map = build_input_json(fields)
    if not input_map:
        return ""
    parts = [f'"{k}": {v}' for k, v in input_map.items()]
    return ", ".join(parts)


def build_code_example(feature: str, subfeature: str, models: list[dict], detail: dict) -> str:
    """Build a quick-start code example from the schema and first available model."""
    if not models:
        return ""

    first_model = models[0]["model"]
    input_fields = detail.get("input_schema", {}).get("fields", [])
    input_json = _format_input_block(input_fields)
    input_curl = _format_curl_input(input_fields)

    mode = detail.get("mode", "sync")
    api_path = "/v3/universal-ai/async" if mode == "async" else "/v3/universal-ai"
    api_url = f"https://api.edenai.run{api_path}"

    if mode == "async":
        mode_note = f"\n> This is an **async** feature. The initial response returns a job ID. Poll `GET /v3/universal-ai/async/{{job_id}}` until the job completes.\n"
    else:
        mode_note = ""

    return f"""{mode_note}
<CodeGroup>
```python Python
import requests

url = "{api_url}"
headers = {{
    "Authorization": "Bearer YOUR_API_KEY",
    "Content-Type": "application/json"
}}

payload = {{
    "model": "{first_model}",
    "input": {input_json}
}}

response = requests.post(url, headers=headers, json=payload)
print(response.json())
```

```bash cURL
curl -X POST {api_url} \\
  -H "Authorization: Bearer YOUR_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{{
    "model": "{first_model}",
    "input": {{{input_curl}}}
  }}'
```
</CodeGroup>
"""


def generate_subfeature_page(feature: str, subfeature_info: dict, detail: dict) -> str:
    """Generate the full MDX content for a single subfeature page."""
    sf_name = subfeature_info["name"]
    fullname = subfeature_info.get("fullname", sf_name)
    description = subfeature_info.get("description", "")
    mode = subfeature_info.get("mode", "sync")
    models = subfeature_info.get("models", [])

    endpoint_method = "POST"
    endpoint_path = "/v3/universal-ai/async" if mode == "async" else "/v3/universal-ai"
    mode_label = "sync" if mode == "sync" else "async"

    input_fields = detail.get("input_schema", {}).get("fields", [])
    output_fields = detail.get("output_schema", {}).get("fields", [])

    code_example = build_code_example(feature, sf_name, models, detail)

    safe_title = escape_frontmatter(fullname)
    safe_desc = escape_frontmatter(truncate_at_word(description, 200))

    page = f"""---
title: "{safe_title}"
description: "{safe_desc}"
---

## Endpoint

`{endpoint_method} {endpoint_path}` ({mode_label})

Model string pattern: `{feature}/{sf_name}/{{provider}}[/{{model}}]`

## Input

{render_schema_table(input_fields)}

## Output

{render_schema_table(output_fields)}

## Available Providers

{render_providers_table(models)}

## Quick Start

{code_example}
"""
    return page


def generate_index_page(features: list[dict]) -> str:
    """Generate the features index page with cards grouped by feature category."""
    sections = []
    for feat in features:
        fname = feat["name"]
        display = derive_display_name(feat)
        icon = derive_icon(fname)

        card_items = []
        for sf in feat.get("subfeatures", []):
            sf_slug = slug(sf["name"])
            sf_fullname = sf.get("fullname", sf["name"])
            sf_desc = sf.get("description", "")
            # Truncate description for card
            short_desc = truncate_at_word(sf_desc, 120)
            card_items.append(
                f'  <Card title="{sf_fullname}" icon="{icon}" href="/v3/expert-models/features/{fname}/{sf_slug}">\n'
                f"    {short_desc}\n"
                f"  </Card>"
            )

        cards_block = "\n".join(card_items)
        sections.append(f"## {display}\n\n<CardGroup cols={{2}}>\n{cards_block}\n</CardGroup>\n")

    all_sections = "\n".join(sections)

    return f"""---
title: "AI Features Reference"
description: "Complete reference for all Universal AI features available through Eden AI."
icon: "microchip"
---

# AI Features Reference

Browse all AI features available through the Universal AI endpoint (`POST /v3/universal-ai`). Each feature page includes input/output schemas, available providers with pricing, and quick-start code examples.

{all_sections}
"""


# --------------------------------
# docs.json navigation update
# --------------------------------


def _build_feature_subgroups(features: list[dict]) -> list[dict]:
    """Build the feature subgroup entries to nest inside Expert Models."""
    subgroups = []
    for feat in features:
        fname = feat["name"]
        display = derive_display_name(feat)
        subpages = []
        for sf in feat.get("subfeatures", []):
            sf_slug = slug(sf["name"])
            subpages.append(f"v3/expert-models/features/{fname}/{sf_slug}")
        subgroups.append({
            "group": f"{display} Features",
            "icon": derive_icon(fname),
            "expanded": False,
            "pages": subpages,
        })
    return subgroups


def update_docs_json(features: list[dict]) -> None:
    """Read docs.json, update the feature subgroups inside Expert Models, write back."""
    with open(DOCS_JSON_PATH, "r") as f:
        docs = json.load(f)

    feature_subgroups = _build_feature_subgroups(features)

    # Find V3 Documentation tab → its groups → Expert Models group
    versions = docs.get("navigation", {}).get("versions", [])
    for version in versions:
        if version.get("version") != "V3":
            continue
        tabs = version.get("tabs", [])
        for tab in tabs:
            if tab.get("tab") != "V3 Documentation":
                continue
            groups = tab.get("groups", [])
            for group in groups:
                if group.get("group") != "V3 Documentation":
                    continue
                pages = group.get("pages", [])

                # Remove old standalone "AI Features" entry if present
                pages[:] = [
                    p for p in pages
                    if not (isinstance(p, dict) and p.get("group") == "AI Features")
                ]

                # Find the Expert Models group and replace its feature subgroups
                for p in pages:
                    if isinstance(p, dict) and p.get("group") == "Expert Models":
                        expert_pages = p.get("pages", [])
                        # Keep non-feature pages (e.g. fallback, webhooks, listing-models)
                        static_pages = [
                            ep for ep in expert_pages
                            if isinstance(ep, str)
                        ]
                        # Replace with static pages + new feature subgroups
                        p["pages"] = static_pages + feature_subgroups
                        break

    # Atomic write: write to temp file then replace, so a crash can't corrupt docs.json
    fd, tmp_path = tempfile.mkstemp(dir=DOCS_JSON_PATH.parent, suffix=".json")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(docs, f, indent=2)
            f.write("\n")
        os.replace(tmp_path, DOCS_JSON_PATH)
    except BaseException:
        os.unlink(tmp_path)
        raise


# ------------------------
# Cleanup stale pages
# ------------------------


def cleanup_stale_pages(features: list[dict]) -> None:
    """Remove .mdx files under v3/expert-models/features/ that no longer map to an API feature."""
    expected_files: set[Path] = {FEATURES_DIR / "index.mdx"}
    for feat in features:
        fname = feat["name"]
        for sf in feat.get("subfeatures", []):
            sf_slug = slug(sf["name"])
            expected_files.add(FEATURES_DIR / fname / f"{sf_slug}.mdx")

    if not FEATURES_DIR.exists():
        return

    for mdx_file in FEATURES_DIR.rglob("*.mdx"):
        if mdx_file not in expected_files:
            print(f"  Removing stale page: {mdx_file.relative_to(DOCS_ROOT)}")
            mdx_file.unlink()

    # Remove empty subdirectories
    for dirpath in sorted(FEATURES_DIR.rglob("*"), reverse=True):
        if dirpath.is_dir() and not any(dirpath.iterdir()):
            dirpath.rmdir()


# ----------
# Main
# ----------


def main() -> None:
    print("Fetching features from API...")
    features = fetch_all_features()
    print(f"  Found {len(features)} feature categories")

    if not features:
        print("ERROR: API returned no features. Aborting to avoid deleting existing pages.")
        raise SystemExit(1)

    total_subfeatures = sum(len(f.get("subfeatures", [])) for f in features)
    print(f"  Total subfeatures: {total_subfeatures}")

    # Ensure output directories exist
    FEATURES_DIR.mkdir(parents=True, exist_ok=True)

    # Generate per-subfeature pages
    for feat in features:
        fname = feat["name"]
        feat_dir = FEATURES_DIR / fname
        feat_dir.mkdir(parents=True, exist_ok=True)

        for sf in feat.get("subfeatures", []):
            sf_name = sf["name"]
            sf_slug = slug(sf_name)
            print(f"  Generating {fname}/{sf_slug}.mdx ...")

            # Fetch detailed schema
            try:
                detail = fetch_subfeature_detail(fname, sf_name)
            except Exception as e:
                print(f"    Warning: could not fetch detail for {fname}/{sf_name}: {e}")
                detail = {}

            content = generate_subfeature_page(fname, sf, detail)
            (feat_dir / f"{sf_slug}.mdx").write_text(content)
    print("  Generating index page...")
    index_content = generate_index_page(features)
    (FEATURES_DIR / "index.mdx").write_text(index_content)

    print("  Cleaning up stale pages...")
    cleanup_stale_pages(features)

    print("  Updating docs.json navigation...")
    update_docs_json(features)

    print(f"Done! Generated {total_subfeatures} feature pages + index.")


if __name__ == "__main__":
    main()
