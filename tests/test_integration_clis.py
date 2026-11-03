"""Runs the real coding agent CLIs with the settings their pages give them.

test_integrations.py sends the request a tool would send. This sends nothing
itself: it runs the tool, with the page's settings written where the tool
reads them, and lets the tool make the request. That is the only check that
catches a page whose settings the tool no longer reads, a key renamed in a
release, a base URL the tool appends a different path to than the page
assumes. Three tools can be installed from npm and run headless, and those
are the three here: Claude Code, Codex and OpenCode.

Everything a tool is given comes from its page: the export lines on the
Claude Code page, the config.toml block on the Codex page, and on the OpenCode
page the script that generates opencode.json, run the way the page tells a
reader to run it. A test adds only what a reader supplies by hand: the API key
where the page leaves a placeholder, and a home directory of its own, so no
setting or credential on the machine running the test can make the tool pass
by talking to something else.

Each tool runs twice. Against the sandbox, which costs nothing and answers
with a canned completion, so what passes is that the tool started, read the
page's settings and got an answer from Eden AI: this runs on every pull
request. And against a real model, with a task that needs the tool's
file-reading tool: read a file holding a random word and reply with it. The
model has to call the tool and the result has to come back through Eden AI,
which is where an agent integration actually breaks. That one spends credits
and runs weekly.
"""

import json
import os
import re
import subprocess
import sys
import tomllib
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from tests.config_blocks import INTEGRATIONS_DIR
from tests.helpers.api import api_base_url
from tests.helpers.protocols import PING, secret
from tests.helpers.script_snippets import TIMEOUT, require_token
from tests.integrations import model_settings, pointed_here, source, unserved_here
from tests.snippet_extractor import (
    API_KEY_RE,
    extract_config_blocks,
    extract_python_blocks,
    extract_shell_blocks,
)

_BIN = Path(__file__).resolve().parent / "clis" / "node_modules" / ".bin"

# Mundane on purpose. "Read this file and repeat it exactly" reads like
# exfiltration to a provider's safety classifier, and Claude Opus refuses it.
_TASK = "What is on the lunch menu today? It is in lunch.txt in this directory."

_EXPORT_RE = re.compile(
    r"^\s*export\s+(?P<name>[A-Z_][A-Z0-9_]*)=(?P<q>[\"']?)(?P<value>.*?)(?P=q)"
    r"\s*(?:#.*)?$",
    re.MULTILINE,
)
_ENV_API_KEY_RE = re.compile(r'"apiKey":\s*"(?P<ref>\{env:(?P<var>\w+)\})"')

# The OpenCode page's script only reads the catalog and writes a file. Its
# limit and the tool's both fit inside the test's, so whichever runs out first
# reports what it was doing, rather than pytest-timeout's bare "Timeout".
_GENERATOR_TIMEOUT = 60


@dataclass
class Run:
    """What to pass the tool, and how to read its answer off what it prints.

    `models` are the ones the page configures the tool with, so a run against
    an API that lacks one can say so rather than fail on it.
    """

    args: list[str]
    env: dict[str, str]
    answer: Callable[[str], str] = str.strip
    models: list[str] = field(default_factory=list)


def _environment(home: Path) -> dict[str, str]:
    """A bare environment, so the only credential the tool can find is ours.

    Not os.environ: a developer's own ANTHROPIC_API_KEY or OPENAI_API_KEY
    would let the tool succeed against the vendor, and the test would pass
    with the page's settings never read.
    """
    return {
        "PATH": os.environ["PATH"],
        "HOME": str(home),
        "XDG_CONFIG_HOME": str(home / ".config"),
        "XDG_DATA_HOME": str(home / ".local" / "share"),
        "XDG_CACHE_HOME": str(home / ".cache"),
        "XDG_STATE_HOME": str(home / ".local" / "state"),
        "LANG": "C.UTF-8",
        "TERM": "dumb",
        "NO_COLOR": "1",
    }


def _exports(page: Path) -> dict[str, str]:
    """The variables the page has the reader export, first value winning.

    The setup block comes first, and the alternatives a page offers further
    down ("or switch to this model") export the same names again.
    """
    found: dict[str, str] = {}
    for block in extract_shell_blocks(page):
        for match in _EXPORT_RE.finditer(block["code"]):
            found.setdefault(match.group("name"), match.group("value"))
    return found


# --- one function per tool --------------------------------------------------


def _claude_code(page: Path, home: Path, token: str, prompt: str) -> Run:
    env = {
        name: pointed_here(API_KEY_RE.sub(token, value))
        for name, value in _exports(page).items()
    }
    assert "ANTHROPIC_BASE_URL" in env, (
        f"{page.name} no longer exports ANTHROPIC_BASE_URL"
    )
    env.update(
        {
            "CLAUDE_CONFIG_DIR": str(home / ".claude"),
            # Telemetry, error reports and the update check go to Anthropic,
            # not to Eden AI, and none of them is what the page configures.
            "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
            "DISABLE_AUTOUPDATER": "1",
        }
    )

    def answer(stdout: str) -> str:
        result = json.loads(stdout)
        assert not result.get("is_error"), f"Claude Code reported an error: {result}"
        return result.get("result") or ""

    models = [value for name, value in env.items() if name.endswith("_MODEL")]
    return Run(["-p", prompt, "--output-format", "json"], env, answer, models)


def _codex(page: Path, home: Path, token: str, prompt: str) -> Run:
    configs = [
        (block["code"], settings)
        for block in extract_config_blocks(page)
        if block["lang"] == "toml" and not block["skip"]
        for settings in [tomllib.loads(block["code"])]
        if "model_providers" in settings
    ]
    assert configs, (
        f"{page.name} no longer has a config.toml block with model_providers"
    )
    code, settings = configs[0]
    codex_home = home / ".codex"
    codex_home.mkdir(parents=True)
    (codex_home / "config.toml").write_text(pointed_here(code))

    provider = settings["model_providers"][settings["model_provider"]]
    env = {"CODEX_HOME": str(codex_home), provider["env_key"]: token}
    args = [
        "exec",
        # A key this version of Codex does not recognise is an error rather
        # than silently ignored, which is how a page catches a key renamed in
        # a release.
        "--strict-config",
        "--skip-git-repo-check",
        # The real-model run lets the agent run `cat`, and nothing else.
        "--sandbox",
        "read-only",
        # Plugins are cloned from GitHub in the background, which is traffic
        # the page does not configure and a process that outlives the test.
        "--disable",
        "plugins",
        prompt,
    ]
    models = [settings["model"]] if "model" in settings else []
    return Run(args, env, models=models)


def _opencode(page: Path, home: Path, token: str, prompt: str) -> Run:
    generators = [
        block
        for block in extract_python_blocks(page)
        if "opencode.json" in block["code"]
    ]
    assert generators, f"{page.name} no longer has the script that writes opencode.json"
    # The page has the reader run this script, which reads the live catalog and
    # writes ~/.config/opencode/opencode.json. It is run the same way here,
    # with the home directory pointed at the test's own.
    script = f"the script on {page.name} that writes opencode.json"
    try:
        generated = subprocess.run(
            [sys.executable, "-c", pointed_here(generators[0]["code"])],
            env=_environment(home),
            cwd=home,
            capture_output=True,
            text=True,
            timeout=_GENERATOR_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        pytest.fail(f"{script} did not finish within {_GENERATOR_TIMEOUT}s")
    if generated.returncode != 0:
        pytest.fail(f"{script} exited {generated.returncode}.\n{generated.stderr}")
    config_path = home / ".config" / "opencode" / "opencode.json"
    config = json.loads(config_path.read_text())

    key = _ENV_API_KEY_RE.search(page.read_text(encoding="utf-8"))
    assert key, f"{page.name} no longer says how to read the key from the environment"
    config["provider"]["edenai"]["options"]["apiKey"] = key.group("ref")
    models = [
        setting.value
        for setting in model_settings(page)
        if setting.key == "model" and setting.value.startswith("edenai/")
    ]
    assert models, f"{page.name} no longer says which model to set"
    config["model"] = models[0]
    # Not on the page, and not about Eden AI: the real-model run gives an agent
    # a task, and it may read a file to do it but nothing more.
    config["permission"] = {"edit": "deny", "bash": "deny", "webfetch": "deny"}
    config["autoupdate"] = False
    config_path.write_text(json.dumps(config))

    return Run(["run", prompt], {key.group("var"): token}, models=[config["model"]])


# Keyed by the page each tool's settings come from, with the binary npm
# installs for it.
_TOOLS = {
    "claude-code": ("claude", _claude_code),
    "codex-cli": ("codex", _codex),
    "opencode": ("opencode", _opencode),
}


# --- the tests ---------------------------------------------------------------


@pytest.mark.execute
@pytest.mark.timeout(_GENERATOR_TIMEOUT + TIMEOUT + 30)
@pytest.mark.parametrize("real_model", [False, True], ids=["sandbox", "real-model"])
@pytest.mark.parametrize("tool", sorted(_TOOLS))
def test_the_tool_answers_through_eden_ai_with_its_pages_settings(
    tool, real_model, tmp_path
):
    binary_name, configure = _TOOLS[tool]
    binary = _BIN / binary_name
    if not binary.exists():
        pytest.skip(f"{binary_name} not installed: run npm ci in tests/clis/")
    token = require_token(paid=real_model)
    page = INTEGRATIONS_DIR / f"{tool}.mdx"

    home, work = tmp_path / "home", tmp_path / "work"
    home.mkdir()
    work.mkdir()
    if real_model:
        word = secret()
        (work / "lunch.txt").write_text(f"Today's soup: {word}\n")

    run = configure(page, home, token, _TASK if real_model else PING)
    missing = unserved_here(run.models)
    if missing:
        pytest.skip(f"{api_base_url()} does not serve {missing}")
    try:
        result = subprocess.run(
            [str(binary), *run.args],
            cwd=work,
            env={**_environment(home), **run.env},
            capture_output=True,
            text=True,
            timeout=TIMEOUT,
            stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired:
        pytest.fail(f"{tool} did not finish within {TIMEOUT}s")

    # The token in either is hidden by conftest, as everywhere in a report.
    printed = f"--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
    where = f"{tool}, configured as {source(page)} says,"
    if result.returncode != 0:
        pytest.fail(f"{where} exited {result.returncode}.\n{printed}")
    try:
        answer = run.answer(result.stdout)
    except ValueError as error:
        pytest.fail(
            f"{where} printed something other than its answer: {error}\n{printed}"
        )
    if real_model:
        assert word in answer, (
            f"{where} was asked what a file holds ({word!r}), and its answer "
            f"does not say. Either the tool call or its result did not make it "
            f"through.\n{printed}"
        )
    else:
        assert answer, f"{tool} exited cleanly and printed no answer.\n{printed}"
