"""Unit tests for the block extractor itself.

These never touch the network or the real docs tree: each one writes a small
.mdx file and asserts on what comes back, so a change to the fence or marker
rules fails here rather than silently changing which snippets get tested.
"""

import os
import subprocess
from pathlib import Path


from tests.snippet_extractor import (
    build_shell_script,
    extract_all_shell,
    extract_python_blocks,
    extract_shell_blocks,
)


def write_page(tmp_path, body: str):
    page = tmp_path / "page.mdx"
    page.write_text(body, encoding="utf-8")
    return page


def test_marker_above_a_codegroup_covers_a_later_fence_in_it(tmp_path):
    """A group is marked as a whole, so the marker cannot be first-tab only."""
    page = write_page(
        tmp_path,
        "{/* skip-test: the whole group is illustrative */}\n"
        "<CodeGroup>\n"
        "```javascript JavaScript\n"
        "console.log(1);\n"
        "```\n"
        "```python Python\n"
        "print(1)\n"
        "```\n"
        "</CodeGroup>\n",
    )

    blocks = extract_python_blocks(page)

    assert len(blocks) == 1
    assert blocks[0]["skip"] is True
    assert blocks[0]["skip_reason"] == "the whole group is illustrative"


def test_shell_blocks_are_extracted_with_their_markers(tmp_path):
    """bash, sh and shell fences come back the way python fences do."""
    page = write_page(
        tmp_path,
        "```bash cURL\n"
        "curl https://api.edenai.run/v3/models\n"
        "```\n"
        "\n"
        "{/* skip-test: needs a server on localhost */}\n"
        "```sh\n"
        "curl http://localhost:3000/\n"
        "```\n",
    )

    blocks = extract_shell_blocks(page)

    assert [b["skip"] for b in blocks] == [False, True]
    assert blocks[0]["code"].strip() == "curl https://api.edenai.run/v3/models"
    assert blocks[1]["skip_reason"] == "needs a server on localhost"


def test_shell_and_python_fences_do_not_leak_into_each_other(tmp_path):
    """A page mixing both languages gives each extractor only its own blocks."""
    page = write_page(
        tmp_path,
        "```python Python\nprint(1)\n```\n\n```bash cURL\ncurl https://x/\n```\n",
    )

    assert len(extract_python_blocks(page)) == 1
    assert len(extract_shell_blocks(page)) == 1


CURL_BLOCK = {
    "code": "curl https://api.edenai.run/v3/models \\\n"
    '  -H "Authorization: Bearer YOUR_API_KEY"\n',
    "paid": False,
}


def test_shell_script_swaps_the_placeholder_key_for_the_token_variable():
    script = build_shell_script(CURL_BLOCK, "v3/llms/models.mdx")

    assert "YOUR_API_KEY" not in script
    assert 'Bearer $EDEN_AI_SANDBOX_API_TOKEN"' in script


def test_shell_script_points_the_hardcoded_host_at_the_configured_base_url():
    script = build_shell_script(CURL_BLOCK, "v3/llms/models.mdx")

    assert "https://api.edenai.run" not in script
    assert "$EDEN_AI_BASE_URL/v3/models" in script


def test_shell_script_swaps_the_management_placeholder_whatever_the_page():
    block = {"code": 'curl -H "Authorization: Bearer YOUR_MANAGEMENT_KEY" x\n'}

    script = build_shell_script(block, "v3/llms/models.mdx")

    assert 'Bearer $EDEN_AI_MANAGEMENT_KEY"' in script


def test_shell_script_turns_an_http_error_into_a_failing_exit_code():
    """curl exits 0 on a 500 unless asked otherwise, so the shim asks."""
    script = build_shell_script(CURL_BLOCK, "v3/llms/models.mdx")

    assert "set -euo pipefail" in script
    assert "--fail-with-body" in script
    # The command from the page is never rewritten, only wrapped.
    assert "curl https://api.edenai.run" not in script
    assert "$EDEN_AI_BASE_URL/v3/models \\" in script


def test_shell_script_resolves_installs_without_installing_anything():
    block = {"code": "pip install 'any-llm-sdk[edenai]'\n"}

    script = build_shell_script(block, "v3/integrations/any-llm.mdx")

    assert "--dry-run" in script
    assert "pip install 'any-llm-sdk[edenai]'" in script


def test_shell_script_resolves_npm_installs_without_installing_anything():
    block = {"code": "npm install -g lynkr\n"}

    script = build_shell_script(block, "v3/integrations/lynkr.mdx")

    assert "--dry-run" in script
    assert "npm install -g lynkr" in script


def test_a_placeholder_inside_a_single_quoted_payload_still_reaches_the_command(
    tmp_path,
):
    """Almost every curl body is -d '{...}', and $VAR does not expand there."""
    block = {"code": 'echo \'{"file": "YOUR_FILE_UUID_OR_URL"}\'\n'}
    script = tmp_path / "block.sh"
    script.write_text(build_shell_script(block, "v3/x.mdx"))

    result = subprocess.run(
        ["bash", str(script)],
        capture_output=True,
        text=True,
        timeout=30,
        env={**os.environ, "_EDEN_TEST_FILE_ID": "a-real-file-id"},
    )

    assert result.returncode == 0, result.stderr
    assert '{"file": "a-real-file-id"}' in result.stdout


def test_an_image_feature_is_handed_the_uploaded_image_not_the_pdf():
    """One shared upload cannot serve both: an image model rejects a PDF."""
    block = {
        "code": 'curl x -d \'{"model": "image/face_detection/amazon", '
        '"input": {"file": "YOUR_FILE_UUID_OR_URL"}}\'\n'
    }

    script = build_shell_script(block, "v3/expert-models/features/image/x.mdx")

    assert "$_EDEN_TEST_IMAGE_ID" in script
    assert "$_EDEN_TEST_FILE_ID" not in script


def test_a_document_feature_still_gets_the_uploaded_pdf():
    block = {
        "code": 'curl x -d \'{"model": "ocr/ocr/amazon", '
        '"input": {"file": "YOUR_FILE_UUID_OR_URL"}}\'\n'
    }

    script = build_shell_script(block, "v3/expert-models/features/ocr/x.mdx")

    assert "$_EDEN_TEST_FILE_ID" in script


def test_a_retired_endpoint_fails_the_script_rather_than_passing_quietly(tmp_path):
    """The whole runner rests on this: curl alone exits 0 on a 404."""
    block = {"code": "curl $EDEN_AI_BASE_URL/v3/definitely-not-a-route\n"}
    script = tmp_path / "block.sh"
    script.write_text(build_shell_script(block, "v3/x.mdx"))

    result = subprocess.run(
        ["bash", str(script)],
        capture_output=True,
        text=True,
        timeout=60,
        env={**os.environ, "EDEN_AI_BASE_URL": "https://api.edenai.run"},
    )

    assert result.returncode != 0, f"a 404 passed: {result.stdout}"


def test_extract_all_shell_writes_one_script_per_block_in_the_docs():
    blocks = extract_all_shell()

    assert blocks, "the published docs contain shell blocks"
    first = blocks[0]
    assert set(first) >= {
        "source_mdx",
        "block_index",
        "script_path",
        "skip",
        "skip_reason",
        "paid",
        "needs_management_key",
    }
    assert Path(first["script_path"]).read_text().startswith("#!/usr/bin/env bash")


def test_extract_all_shell_flags_the_blocks_that_need_a_management_key():
    """The Management API pages carry curl samples, and they need that key."""
    blocks = extract_all_shell()

    needing = [b for b in blocks if b["needs_management_key"]]

    assert needing
    assert all(
        "$EDEN_AI_MANAGEMENT_KEY" in Path(b["script_path"]).read_text() for b in needing
    )


# Spelled out rather than shared with the extractor, so this stays a real
# check on the generated scripts and not a restatement of the rule that
# produced them.
STATEFUL_COMMANDS = (
    "docker ",
    "git clone",
    "sudo ",
    "systemctl ",
    "npm run ",
    "chmod ",
    "chown ",
    "rm -rf",
)


def test_no_generated_script_touches_local_state():
    """A test run must not start containers, clone repos or reset passwords.

    Several integration pages drive somebody else's software. Naming the Eden
    AI URL is not the same as calling it: one open-webui sample passes it to
    `docker run` as an environment variable.
    """
    offenders = [
        (block["source_mdx"], command)
        for block in extract_all_shell()
        for command in STATEFUL_COMMANDS
        if command in Path(block["script_path"]).read_text()
    ]

    assert offenders == []


def test_a_real_eden_call_on_an_integration_page_is_still_covered():
    """Excluding the tooling must not exclude the API call next to it."""
    pages = {b["source_mdx"] for b in extract_all_shell()}

    assert "v3/integrations/open-webui.mdx" in pages


def test_extract_all_shell_keeps_eden_ai_calls_and_plain_installs():
    blocks = extract_all_shell()

    scripts = {b["source_mdx"]: Path(b["script_path"]).read_text() for b in blocks}

    assert any("$EDEN_AI_BASE_URL" in text for text in scripts.values())
    assert any("pip install" in text for text in scripts.values())


def test_extract_all_shell_leaves_out_an_install_straight_from_a_git_repo():
    """A git+ install clones the repo and runs its setup.py to resolve."""
    blocks = extract_all_shell()

    assert not any("git+https" in Path(b["script_path"]).read_text() for b in blocks)
