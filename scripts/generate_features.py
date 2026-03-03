#!/usr/bin/env python3
"""
Generate Mintlify MDX documentation pages from the Eden AI /v3/info API.

Usage:
    python scripts/generate_features.py

No dependencies beyond Python stdlib are required.
"""

import json
import os
import shutil
import urllib.request
from pathlib import Path

# --------------------------
# Configuration
# --------------------------
API_BASE = "https://api.edenai.run"
INFO_ENDPOINT = f"{API_BASE}/v3/info"

# Root of the Mintlify docs site (where docs.json lives)
DOCS_ROOT = Path(__file__).resolve().parent.parent
FEATURES_DIR = DOCS_ROOT / "v3" / "features"
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


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


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


def input_type_for_feature(feature: str, detail: dict) -> str:
    """Determine the sample input type (text, file, etc.) from the schema."""
    fields = detail.get("input_schema", {}).get("fields", [])
    field_names = {f["name"] for f in fields}
    if "text" in field_names:
        return "text"
    if "file" in field_names:
        return "file"
    if "texts" in field_names:
        return "texts"
    return "text"


# ---------------------------------------------------------------------------
# MDX generation
# ---------------------------------------------------------------------------


def render_schema_table(fields: list[dict], indent: int = 0) -> str:
    """Render a list of schema fields as a Markdown table."""
    if not fields:
        return "_No schema information available._\n"

    lines = [
        "| Field | Type | Required | Description |",
        "|-------|------|----------|-------------|",
    ]
    for f in fields:
        name = f.get("name", "")
        ftype = f.get("type", "")
        required = "Yes" if f.get("required") else "No"
        desc = f.get("description", "")
        # For array types, annotate the item type
        if ftype == "array" and "items" in f:
            item_type = f["items"].get("type", "")
            ftype = f"array[{item_type}]" if item_type else "array"
        lines.append(f"| {name} | {ftype} | {required} | {desc} |")
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


def build_code_example(feature: str, subfeature: str, models: list[dict], detail: dict) -> str:
    """Build a quick-start code example using the first available model."""
    if not models:
        return ""

    first_model = models[0]["model"]
    input_type = input_type_for_feature(feature, detail)

    if input_type == "text":
        input_json = '{\n        "text": "Your text here"\n    }'
        input_curl = '"text": "Your text here"'
    elif input_type == "texts":
        input_json = '{\n        "texts": ["First text", "Second text"]\n    }'
        input_curl = '"texts": ["First text", "Second text"]'
    elif input_type == "file":
        input_json = '{\n        "file": "YOUR_FILE_UUID_OR_URL"\n    }'
        input_curl = '"file": "YOUR_FILE_UUID_OR_URL"'
    else:
        input_json = '{}'
        input_curl = ''

    mode = detail.get("mode", "sync")
    if mode == "async":
        mode_note = "\n> This is an **async** feature. The initial response returns a job ID. Poll `GET /v3/universal-ai/{job_id}` until the job completes.\n"
    else:
        mode_note = ""

    return f"""{mode_note}
<CodeGroup>
```python Python
import requests

url = "https://api.edenai.run/v3/universal-ai"
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
curl -X POST https://api.edenai.run/v3/universal-ai \\
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
    endpoint_path = "/v3/universal-ai"
    mode_label = "sync" if mode == "sync" else "async"

    input_fields = detail.get("input_schema", {}).get("fields", [])
    output_fields = detail.get("output_schema", {}).get("fields", [])

    code_example = build_code_example(feature, sf_name, models, detail)

    page = f"""---
title: "{fullname}"
description: "{description[:200]}"
icon: "{DEFAULT_SUBFEATURE_ICON}"
---

# {fullname}

{description}

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
            short_desc = sf_desc[:120] + "..." if len(sf_desc) > 120 else sf_desc
            card_items.append(
                f'  <Card title="{sf_fullname}" icon="{icon}" href="/v3/features/{fname}/{sf_slug}">\n'
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


# ---------------------------------------------------------------------------
# docs.json navigation update
# ---------------------------------------------------------------------------


def build_nav_group(features: list[dict]) -> dict:
    """Build the 'AI Features' navigation group for docs.json."""
    pages: list = ["v3/features/index"]
    for feat in features:
        fname = feat["name"]
        display = derive_display_name(feat)
        subpages = []
        for sf in feat.get("subfeatures", []):
            sf_slug = slug(sf["name"])
            subpages.append(f"v3/features/{fname}/{sf_slug}")
        pages.append({"group": display, "icon": derive_icon(fname), "pages": subpages})
    return {"group": "AI Features", "icon": "microchip", "pages": pages}


def update_docs_json(features: list[dict]) -> None:
    """Read docs.json, add/update the AI Features navigation group, write back."""
    with open(DOCS_JSON_PATH, "r") as f:
        docs = json.load(f)

    nav_group = build_nav_group(features)

    # Find V3 Documentation tab → its groups[0] → pages array (the top-level groups list)
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

                # Remove old AI Features entry if present
                pages[:] = [
                    p for p in pages
                    if not (isinstance(p, dict) and p.get("group") == "AI Features")
                ]

                # Remove text-features, ocr-features, image-features from
                # Universal AI group (superseded by per-feature pages).
                # The Universal AI group is nested inside "How-To Guides".
                removed_pages = {
                    "v3/how-to/universal-ai/text-features",
                    "v3/how-to/universal-ai/ocr-features",
                    "v3/how-to/universal-ai/image-features",
                }
                for p in pages:
                    if isinstance(p, dict) and p.get("group") == "How-To Guides":
                        for sub in p.get("pages", []):
                            if isinstance(sub, dict) and sub.get("group") == "Universal AI":
                                sub["pages"] = [
                                    pg for pg in sub.get("pages", [])
                                    if pg not in removed_pages
                                ]

                # Insert AI Features after the How-To Guides group
                insert_idx = None
                for i, p in enumerate(pages):
                    if isinstance(p, dict) and p.get("group") == "How-To Guides":
                        insert_idx = i + 1
                        break
                if insert_idx is not None:
                    pages.insert(insert_idx, nav_group)
                else:
                    # Fallback: insert before Tutorials or at end
                    pages.append(nav_group)

    with open(DOCS_JSON_PATH, "w") as f:
        json.dump(docs, f, indent=2)
        f.write("\n")


# ---------------------------------------------------------------------------
# Cleanup stale pages
# ---------------------------------------------------------------------------


def cleanup_stale_pages(features: list[dict]) -> None:
    """Remove .mdx files under v3/features/ that no longer map to an API feature."""
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


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    print("Fetching features from API...")
    features = fetch_all_features()
    print(f"  Found {len(features)} feature categories")

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

    # Generate index page
    print("  Generating index page...")
    index_content = generate_index_page(features)
    (FEATURES_DIR / "index.mdx").write_text(index_content)

    # Clean up stale pages
    print("  Cleaning up stale pages...")
    cleanup_stale_pages(features)

    # Update docs.json navigation
    print("  Updating docs.json navigation...")
    update_docs_json(features)

    print(f"Done! Generated {total_subfeatures} feature pages + index.")


if __name__ == "__main__":
    main()
