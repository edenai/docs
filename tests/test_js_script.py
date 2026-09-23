"""Unit tests for the JavaScript and TypeScript snippet runner.

These never touch the network or the docs tree: each one hands a small block
to the script builder and asserts on what comes back, so a change to the
placeholder or module-format rules fails here rather than silently changing
which snippets get tested.
"""

import os
import subprocess
from pathlib import Path

from tests.snippet_extractor import extract_js_blocks, mdx_files

from tests.js_script import (
    build_js_script,
    extract_all_js,
    script_suffix,
    unrunnable_reason,
)

# Every test here reads the same extraction. Each call re-walks the docs
# tree and rewrites every script, once per xdist worker, so it is done once.
BLOCKS = extract_all_js()

ESM_FETCH_BLOCK = {
    "code": "const response = await fetch('https://api.edenai.run/v3/models', {\n"
    "  headers: { 'Authorization': 'Bearer YOUR_API_KEY' }\n"
    "});\n"
    "console.log(await response.json());\n",
    "lang": "javascript",
    "paid": False,
}


def run_script(tmp_path, block, source_mdx="v3/llms/models.mdx", env=None):
    """Write one generated script out and run it with node."""
    script = tmp_path / f"block{script_suffix(block)}"
    script.write_text(build_js_script(block, source_mdx), encoding="utf-8")
    return subprocess.run(
        ["node", str(script)],
        capture_output=True,
        text=True,
        timeout=60,
        stdin=subprocess.DEVNULL,
        env={**os.environ, **(env or {})},
    )


# --- module format -------------------------------------------------------


def test_an_import_block_becomes_an_esm_script():
    """Top-level await is everywhere in these samples, so ESM is the default."""
    block = {"code": "import OpenAI from 'openai';\n", "lang": "javascript"}

    assert script_suffix(block) == ".mjs"


def test_a_require_block_becomes_a_commonjs_script():
    block = {"code": "const OpenAI = require('openai');\n", "lang": "javascript"}

    assert script_suffix(block) == ".cjs"


def test_a_typescript_block_keeps_its_language_in_the_extension():
    """node strips the types itself, but only for a .mts or .cts file."""
    esm = {"code": "import OpenAI from 'openai';\n", "lang": "typescript"}
    cjs = {"code": "const OpenAI = require('openai');\n", "lang": "typescript"}

    assert script_suffix(esm) == ".mts"
    assert script_suffix(cjs) == ".cts"


def test_a_block_with_neither_import_nor_require_is_esm():
    """A bare fetch sample needs top-level await, which CommonJS has not got."""
    assert script_suffix(ESM_FETCH_BLOCK) == ".mjs"


# --- placeholders --------------------------------------------------------


def test_a_placeholder_in_a_single_quoted_string_becomes_a_template_literal():
    """JavaScript interpolates nothing in a plain quote, so the quote changes."""
    script = build_js_script(ESM_FETCH_BLOCK, "v3/llms/models.mdx")

    assert "YOUR_API_KEY" not in script
    assert "`Bearer ${process.env.EDEN_AI_SANDBOX_API_TOKEN}`" in script


def test_a_placeholder_in_a_double_quoted_string_becomes_a_template_literal():
    block = {
        "code": 'const headers = { "Authorization": "Bearer YOUR_API_KEY" };\n',
        "lang": "javascript",
    }

    script = build_js_script(block, "v3/llms/models.mdx")

    assert "`Bearer ${process.env.EDEN_AI_SANDBOX_API_TOKEN}`" in script


def test_a_placeholder_already_in_a_template_literal_is_spliced_in_place():
    """Converting an existing template literal again would double its quotes."""
    block = {
        "code": "const auth = `Bearer YOUR_API_KEY`;\n",
        "lang": "javascript",
    }

    script = build_js_script(block, "v3/llms/models.mdx")

    assert "`Bearer ${process.env.EDEN_AI_SANDBOX_API_TOKEN}`" in script
    assert "``" not in script


def test_a_placeholder_outside_any_string_is_referenced_directly():
    block = {"code": "const key = YOUR_API_KEY;\n", "lang": "javascript"}

    script = build_js_script(block, "v3/llms/models.mdx")

    assert "const key = process.env.EDEN_AI_SANDBOX_API_TOKEN;" in script


def test_the_hardcoded_host_is_replaced_by_the_configured_base_url():
    script = build_js_script(ESM_FETCH_BLOCK, "v3/llms/models.mdx")

    assert "https://api.edenai.run" not in script
    assert "`${process.env.EDEN_AI_BASE_URL}/v3/models`" in script


def test_the_management_placeholder_becomes_the_management_key():
    block = {
        "code": "const headers = { Authorization: 'Bearer YOUR_MANAGEMENT_KEY' };\n",
        "lang": "javascript",
    }

    script = build_js_script(block, "v3/general/sandbox.mdx")

    assert "`Bearer ${process.env.EDEN_AI_MANAGEMENT_KEY}`" in script


def test_an_image_feature_is_handed_the_uploaded_image_not_the_pdf():
    """One shared upload cannot serve both: an image model rejects a PDF."""
    block = {
        "code": 'const body = { "model": "image/face_detection/amazon", '
        '"input": { "file": "YOUR_FILE_UUID_OR_URL" } };\n',
        "lang": "javascript",
    }

    script = build_js_script(block, "v3/expert-models/features/image/x.mdx")

    assert "process.env._EDEN_TEST_IMAGE_ID" in script
    assert "_EDEN_TEST_FILE_ID" not in script


def test_a_document_feature_still_gets_the_uploaded_pdf():
    block = {
        "code": 'const body = { "model": "ocr/ocr/amazon", '
        '"input": { "file": "YOUR_FILE_UUID_OR_URL" } };\n',
        "lang": "javascript",
    }

    script = build_js_script(block, "v3/expert-models/features/ocr/x.mdx")

    assert "process.env._EDEN_TEST_FILE_ID" in script


# --- the rewritten script actually works ---------------------------------


def test_a_generated_script_really_interpolates_the_environment(tmp_path):
    """The rewrite is only correct if node resolves it at runtime."""
    block = {
        "code": "console.log(JSON.stringify({ file: 'YOUR_FILE_UUID_OR_URL' }));\n",
        "lang": "javascript",
    }

    result = run_script(tmp_path, block, env={"_EDEN_TEST_FILE_ID": "a-real-file-id"})

    assert result.returncode == 0, result.stderr
    assert '{"file":"a-real-file-id"}' in result.stdout


def test_a_retired_endpoint_fails_the_script_rather_than_passing_quietly(tmp_path):
    """The whole runner rests on this: fetch resolves happily on a 404."""
    block = {
        "code": "const r = await fetch('https://api.edenai.run/v3/definitely-not-a-route');\n"
        "console.log(await r.json());\n",
        "lang": "javascript",
    }

    result = run_script(
        tmp_path, block, env={"EDEN_AI_BASE_URL": "https://api.edenai.run"}
    )

    assert result.returncode != 0, f"a 404 passed: {result.stdout}"


# --- which blocks the suite is willing to run ----------------------------


def test_a_plain_fetch_block_is_runnable():
    assert unrunnable_reason(ESM_FETCH_BLOCK["code"]) == ""


def test_a_block_importing_a_package_we_do_not_install_says_which_one():
    """The reason names the package, so the reader knows what to do about it."""
    react = "import { useState } from 'react';\n"

    assert unrunnable_reason(react) == (
        "imports react, which the runner does not install"
    )


def test_a_block_importing_a_package_we_do_install_is_runnable():
    assert unrunnable_reason("import OpenAI from 'openai';\n") == ""


def test_a_node_builtin_is_not_mistaken_for_a_missing_package():
    assert unrunnable_reason("import crypto from 'node:crypto';\n") == ""


def test_a_block_shelling_out_is_not_runnable():
    """A doc sample must not be able to run other software on the runner.

    child_process is a builtin, so allowlisting node wholesale would let a
    future sample do what the shell rules refuse to let a bash block do.
    """
    code = "import { execSync } from 'node:child_process';\n"

    assert unrunnable_reason(code) != ""


def test_a_browser_sample_carries_a_marker_rather_than_being_detected():
    """A block node cannot run for a reason no import shows must say so itself.

    file-upload reads from an <input> element. Nothing about its text makes
    that mechanically detectable without guessing at identifier names, so it
    takes the marker the docs use for every other non-runnable block.
    """
    block = next(
        b
        for b in BLOCKS
        if b["source_mdx"] == "v3/llms/file-upload.mdx" and b["block_index"] == 1
    )

    assert block["skip"] is True
    assert "input" in block["skip_reason"]


def test_an_empty_block_is_not_runnable():
    assert unrunnable_reason("\n  \n") != ""


def test_a_sample_reading_the_key_from_the_environment_is_pointed_at_the_test_token():
    """The SDK pages skip the placeholder and read process.env directly."""
    block = {
        "code": "const client = new OpenAI({ apiKey: process.env.EDEN_AI_API_KEY });\n",
        "lang": "typescript",
    }

    script = build_js_script(block, "v3/integrations/openai-sdk-typescript.mdx")

    assert "process.env.EDEN_AI_SANDBOX_API_TOKEN" in script
    assert "process.env.EDEN_AI_API_KEY" not in script


def test_an_environment_read_inside_a_template_literal_is_not_wrapped_again():
    """It is already an expression, so the quoting rules must leave it alone."""
    block = {
        "code": "const auth = `Bearer ${process.env.EDEN_AI_API_KEY}`;\n",
        "lang": "javascript",
    }

    script = build_js_script(block, "v3/integrations/openai-sdk-typescript.mdx")

    assert "`Bearer ${process.env.EDEN_AI_SANDBOX_API_TOKEN}`" in script
    assert "${${" not in script


# --- the generated tree, over the real docs -------------------------------


def test_extract_all_js_writes_one_script_per_block_in_the_docs():
    blocks = BLOCKS

    assert blocks, "the published docs contain JavaScript blocks"
    first = blocks[0]
    assert set(first) >= {
        "source_mdx",
        "block_index",
        "lang",
        "script_path",
        "skip",
        "paid",
        "needs_management_key",
    }
    assert Path(first["script_path"]).read_text().startswith("// Auto-generated")


# Spelled out rather than derived from js_script, so this stays a real check on
# the generated scripts and not a restatement of the rule that produced them.
UNAVAILABLE_PACKAGES = (
    "react",
    "express",
    "@earendil-works/pi-coding-agent",
    "safe-stable-stringify",
)


def test_a_script_importing_what_we_cannot_install_is_never_left_to_run():
    """It has to be held back, and held back visibly.

    Running it would fail on the import, which reads like a broken doc rather
    than a sample node was never going to run. Dropping it instead would be
    worse: the block would vanish from the output and nobody would know the
    page was only part covered.
    """
    unrunnable = []
    for block in BLOCKS:
        text = Path(block["script_path"]).read_text()
        for package in UNAVAILABLE_PACKAGES:
            if f"'{package}'" in text or f'"{package}"' in text:
                unrunnable.append(block)
                break

    assert unrunnable, "the docs do contain samples the runner cannot run"
    assert all(b["skip"] for b in unrunnable)
    assert all(b["skip_reason"] for b in unrunnable)


def test_no_generated_script_still_carries_an_unresolved_placeholder():
    """A leftover YOUR_... reaches the API as a literal and 401s confusingly."""
    offenders = [
        (block["source_mdx"], line.strip())
        for block in BLOCKS
        for line in Path(block["script_path"]).read_text().splitlines()
        if "YOUR_" in line
    ]

    assert offenders == []


def test_every_js_fence_in_the_docs_is_accounted_for():
    """What the suite reports on and what the docs contain must be one number.

    A block the runner cannot run is reported as skipped, never dropped, so
    the two counts cannot drift apart without a test noticing.
    """
    fences = sum(len(extract_js_blocks(page)) for page in mdx_files())

    assert len(BLOCKS) == fences


def test_a_block_is_marked_as_needing_the_installed_packages():
    """Without node_modules those blocks are skipped, not failed.

    A contributor who has not run npm ci should see them reported as skipped,
    the way a missing token skips the blocks that need one, rather than a wall
    of module-not-found errors that look like broken docs.
    """
    blocks = {(b["source_mdx"], b["block_index"]): b["needs_packages"] for b in BLOCKS}

    assert blocks[("v3/integrations/openai-sdk-typescript.mdx", 1)] is True
    assert blocks[("v3/quickstart/first-llm-call.mdx", 1)] is False
