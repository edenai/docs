# Documentation Snippet Tests

Automated test suite that checks the documentation against reality. It extracts the code snippets from `.mdx` files and executes them against the Eden AI API: Python snippets become importable modules; shell, JavaScript and TypeScript snippets become standalone scripts and are run with bash or node, so what gets tested is the code a reader would paste rather than a translation of it. It also follows every link on every published page, which is the other half of a page being correct.

## Setup

```bash
# Create a virtual environment
uv venv .venv
source .venv/bin/activate

# Install dependencies
uv pip install -r tests/requirements.txt

# The Ask AI eval pipeline (tests/evals/) has its own file, which includes the above
uv pip install -r tests/requirements-evals.txt

# The packages the JavaScript and TypeScript samples import, and the tsc
# that type-checks them. Needs node 24, which strips TypeScript types
# without a flag. Skip this and those suites report as skipped.
npm ci --prefix tests

# The Claude Code, Codex and OpenCode CLIs the integration tests run. About a
# gigabyte of platform binaries, so it has its own manifest; skip it and
# tests/test_integration_clis.py reports as skipped.
npm ci --prefix tests/clis

# Set up environment variables
cp tests/.env.example tests/.env
# Edit tests/.env and fill in your token values
```

**Environment variables:**

| Variable | Required | Description |
|----------|----------|-------------|
| `EDEN_AI_SANDBOX_API_TOKEN` | For execution tests | Sandbox token — AI features return mock responses, no credits consumed |
| `EDEN_AI_PRODUCTION_API_TOKEN` | Optional | Production token, needed by the few pages whose samples require real provider responses (e.g. structured output); skipped if not set |
| `EDEN_AI_MANAGEMENT_KEY` | Optional | Management key (`mgmt-eden-...`, `manage:read` + `manage:write`), needed by Management API samples (custom API keys, sandbox key creation, monitoring). Samples mint real inference keys in the key's organization; the run revokes them on the way out, and clears any left by a cancelled run before it starts. Cleanup only ever touches keys named after the samples (`production-v1`, `team-backend`, `team-daily`, `dev-testing`). Skipped if not set |
| `EDEN_AI_BASE_URL` | Optional | Defaults to `https://staging-api.edenai.run`. CI runs against production. The integration guides that drive Eden AI through a framework holding a hardcoded production endpoint (Haystack) are reported as skipped anywhere else, and so is an integration request or CLI run for a model that API does not serve: the pages are checked against production's catalog |
| `EDEN_AI_RUN_PAID_CALLS` | Optional | Off by default, so neither a docs PR nor a local run bills the account. Set to `1` to also run the samples marked `{/* paid-test */}`, which need the model to answer for real, and the real-model integration checks (every model on the integration pages through its tool's protocol, and the agent CLIs on a real task). CI turns it on for the weekly run and for a manual dispatch, never for a pull request |
| `EDEN_AI_CHECK_EXTERNAL_LINKS` | Optional | Off by default. Set to `1` to also follow the links that leave the docs. They depend on somebody else's site being up, so CI checks them on the weekly run rather than on a pull request |
| `EDEN_AI_SKIP_TEST_UPLOADS` | Optional | Off by default. Set to `1` for a run that executes no snippet, such as the integration checks, to skip the document and image the session uploads for the samples, and the cleanup around them |
| `EDENAI_API_KEY` | Set for you | Not something you fill in: the suite publishes the token above under this name because the integration frameworks (any-llm, Haystack, Atomic Agents) read the key from the environment rather than taking it as an argument |

## Running Tests

```bash
pytest tests/ -v
```

Tests run in parallel by default (via `pytest-xdist`, configured in `pytest.ini` with `-n auto` which matches the CPU count). Each test is capped at 5 minutes (`pytest-timeout`), every `requests` call made by a snippet gets a 120-second timeout unless it sets its own, and 429 retries wait at most 30 seconds, so a request the API never answers fails with its details instead of stalling the run. Override the worker count with `-n`:

```bash
pytest tests/ -v -n 5   # 5 workers
pytest tests/ -v -n 0   # disable parallelism
```

### Tests for a specific doc page

Each `.mdx` file maps to a generated module in `tests/generated/`. The naming convention is path separators become `_` and hyphens become `_`:

```
v3/how-to/universal-ai/text-features.mdx -> tests/generated/v3_how_to_universal_ai_text_features.py
```

To run tests for a single page, use pytest's `-k` filter:

```bash
# All tests for text-features.mdx
pytest tests/ -v -k "text_features"

# A specific block (block_3) from that page
pytest tests/ -v -k "text_features and block_3"
```

### Coverage Report

Coverage is enabled by default (via `tests/pytest.ini`). Every `pytest tests/` run prints a coverage summary showing which snippet lines executed.

```bash
# HTML report (opens in browser)
pytest tests/ --cov-report=html
open tests/htmlcov/index.html
```

Coverage measures the generated snippet modules (`tests/generated/`), showing which documentation code blocks actually executed.

### Debugging in VSCode

A launch configuration is included in `.vscode/launch.json`. Use the **"Debug Snippet Tests"** configuration to run tests with the debugger attached — set breakpoints in generated modules or test infrastructure as needed.

### Inspect what gets extracted

```bash
python tests/snippet_extractor.py
```

## Adding New Documentation

When adding new `.mdx` files with Python code snippets:

1. Use ` ```python ` fencing for code blocks
2. Make each snippet self-contained (include its own imports, define `url`, `headers`, etc.)
   - Use `YOUR_API_KEY` as the inference key placeholder, `YOUR_MANAGEMENT_KEY` for Management API (`/v3/manage/...`) calls, and `YOUR_SANDBOX_TOKEN` where the page is specifically about sandbox tokens; the extractor swaps each for the matching environment variable
3. Run `pytest tests/ -v` to verify
4. The extractor auto-discovers new `.mdx` files (under `v3/` and at the repo root) — no configuration needed

### Shell Snippets

The curl samples are what most readers copy, so they run too. Each block
becomes a script under `tests/generated/sh/` and is run with bash. The command
itself is never rewritten; the script wraps it in shims:

- `curl` gains `--fail-with-body`, because curl exits 0 on a 4xx or 5xx and a
  retired endpoint would otherwise pass in silence.
- `pip` and `npm` gain `--dry-run`, so an install block resolves the package
  against its index and lands nothing in the runner's environment.

Two kinds of block run: a curl call to Eden AI, and a plain install. Everything
else on a page is left alone and never becomes a script, because running it
would drive somebody else's software (`docker compose up`, `git clone`, an
admin password reset). That rule lives in `_is_testable_shell`, and
`tests/test_snippet_extractor.py` asserts no generated script can touch local
state.

Placeholders resolve the same way they do in Python (`YOUR_API_KEY`,
`YOUR_MANAGEMENT_KEY`, `YOUR_SANDBOX_TOKEN`, `YOUR_FILE_UUID_OR_URL`). Almost
every curl body is `-d '{...}'` and the shell expands nothing inside single
quotes, so a placeholder there is spliced as `'"$VAR"'`. The run uploads a
document and an image, and a sample gets whichever its model calls for: an
image model rejects a PDF outright.

### JavaScript and TypeScript Snippets

Every `javascript` and `typescript` fence becomes its own script under
`tests/generated/js/` and is run with node. No build step: a `.mjs` or `.cjs`
runs as it is, and node strips the annotations off a `.mts` or `.cts` on load,
which is why the extension carries the language. A block using `require()` and
no `import` becomes CommonJS; everything else is ESM, because almost every
sample here uses top-level `await`.

`fetch` resolves on a 4xx or 5xx, exactly as curl exits 0 on one, so a block
calling it is wrapped the way a curl block is: the sample is untouched and
`globalThis.fetch` is replaced with one that throws on a failed response. The
SDK blocks raise on their own and keep the real `fetch`.

Placeholders resolve as they do elsewhere, but a JavaScript quote interpolates
nothing, so `'Bearer YOUR_API_KEY'` becomes
`` `Bearer ${process.env.EDEN_AI_SANDBOX_API_TOKEN}` ``: the quotes around the
placeholder change with it. A sample reading `process.env.EDEN_AI_API_KEY`
directly is already an expression and is substituted as it stands.

A block runs only if node can run it at all: everything it imports has to be a
builtin or one of the packages in `tests/package.json`. A React component, an
Express receiver and an editor-extension registration cannot be run, so they
are reported as skipped with the reason naming the package, rather than left
to fail on a missing import or dropped from the run. `unrunnable_reason`
produces that reason, and `tests/test_js_script.py` asserts that every JS fence
in the docs turns up in the suite either way, so what the docs contain and what
the suite looked at cannot quietly drift apart.

The allowlist is read from `tests/package.json` rather than restated, so adding
a package for a new sample is one edit. The builtins are deliberately not
node's whole list: `child_process` and the networking modules would let a
sample run other software on the runner, which is what the shell rules exist to
prevent.

A block node cannot run for a reason no import reveals, such as reading from an
`<input>` element on the page, carries a `{/* skip-test: ... */}` marker like
any other non-runnable block.

The packages are pinned exactly and `tests/package-lock.json` is committed, so
a run tests the docs rather than whatever npm resolved that morning. Install
them with `npm ci` from `tests/`.

#### Type checking

Running a TypeScript block proves it executes; it does not prove it compiles,
because node strips the types rather than checking them. `tsc --noEmit` runs
over the generated `.mts` and `.cts` files against the real SDK typings, so a
renamed option or a field the SDK no longer returns fails here even when the
API tolerates it at runtime. It found two such bugs on its first run.

`strict` is off: a documentation sample is written to be read, not to satisfy
`noImplicitAny`, and turning it on flags an untyped parameter in nearly every
block. `erasableSyntaxOnly` is on, because an `enum` or a `namespace` compiles
fine and then fails the moment somebody runs the sample.

This is also where a TypeScript block is syntax-checked. `node --check` is not
used on it: it falls back to parsing a `.mts` as CommonJS when the file has no
import of its own, and then reports a plain type annotation as a syntax error
in a file node runs quite happily.

### Skipping Non-Runnable Snippets

The same `{/* skip-test */}` and `{/* paid-test */}` markers work for shell, JavaScript and TypeScript blocks. A marker above a `<CodeGroup>` covers every fence in the group, and a marker directly above one fence covers only that fence.

Some ` ```python ` blocks are illustrative fragments (e.g., `"model": "openai/gpt-4o"`) rather than valid standalone Python, and a few depend on something no test environment can supply (a package that has not shipped the code the page documents, a module that only exists inside another project's tree). To exclude a block from testing while preserving syntax highlighting, add an MDX comment before the fence:

```
{/* skip-test */}
```python
"model": "openai/gpt-4o"
```​
```

This also works with `<CodeGroup>` blocks — place the comment before the `<CodeGroup>` tag:

```
{/* skip-test */}
<CodeGroup>
```python Python
# code with known issues...
```​
</CodeGroup>
```

The marker carries the reason, and every marker in the docs has one. It is what
stops the next person re-deciding from scratch whether the block should run:

```
{/* skip-test: the Eden AI provider is merged upstream but not in any aisuite release yet */}
```

The comment is invisible in rendered docs. The extractor checks the 3 lines preceding each ` ```python ` fence for the marker. A fence is a fence whatever tab label follows the language (` ```python OpenAI SDK `) and whatever indentation it sits at inside a `<Step>` or `<Accordion>`, so a block cannot escape the suite by being nested or labelled. Skipped blocks still appear in test output (as `SKIPPED`) rather than being silently excluded, so you can track how many snippets are skipped.

### Snippets That Need a Real Model Answer

The sandbox token serves one canned text completion. That carries any sample
which only reads the message content, but not one that asks the model for
structure: a JSON schema response, a pydantic `output_type`, an Instructor tool
call. Those need a production token and a real inference call, which costs
credits every time it runs.

Mark them, in the same place and the same shape as `skip-test`:

```
{/* paid-test: needs a real model answer, the sandbox returns canned prose */}
```

The marker does two things. It switches that one block to
`EDEN_AI_PRODUCTION_API_TOKEN`, whatever the rest of the page uses, and it holds
the block back unless `EDEN_AI_RUN_PAID_CALLS` is set. So a docs PR and a local
run report it as `SKIPPED` and spend nothing, and the weekly scheduled run
executes it.

Reach for this only when the sandbox genuinely cannot serve the sample. It buys
coverage with money, so a block that would pass on the sandbox should not carry
it.

## Links

`tests/test_links.py` follows every link on every published page: internal
links, relative links to a sibling page, anchors to a section, and images. It
reads files and makes no requests, so it runs on every pull request and needs
nothing set up. It also checks that `docs.json` names no page that has been
deleted, that no published page has become unreachable, meaning nothing in
the navigation and no other page points at it, and that every redirect in
`docs.json` lands on a page and does not start from one that still exists.

`tests/test_links_external.py` needs the network. It has two halves:

- The **OpenAPI specs** `docs.json` points the API reference tabs at. Mintlify
  renders those tabs by fetching the spec, so one that stops resolving, or
  answers with something that is not a spec, empties a section of the site
  without anything in this repository changing. Checked on every run.
- The **external links**, everything the docs send a reader to. Checked only
  when `EDEN_AI_CHECK_EXTERNAL_LINKS` is set, which CI does on the weekly run.
  A pull request should not go red because someone else's site is down.

Working out what is *not* a link is most of the job, so three rules are worth
knowing before you add a check:

- Code is blanked out first, fenced and inline. An MDX page documents MDX, so
  a fence can contain link markup that is an example rather than a link. The
  blanking keeps the line count, so a failure names the line you will open.
- Headings are read from the same blanked text. A Python comment inside a
  fence starts with `#`, and a heading scan that does not blank fences first
  invents headings for a broken anchor to resolve against.
- `#chat` and `#manage-cookies` are not headings. They are click targets bound
  by `intercom-chat.js` and `cookie-consent.js`, listed in `JS_HOOK_ANCHORS`
  in `tests/links.py`. A test reads those scripts to confirm each one really
  is bound, so the allowlist cannot become somewhere a broken anchor hides.

## Page titles and descriptions

A page's frontmatter `title` and `description` are what a search result
shows: the title, with ` - Eden AI Documentation` appended, and the snippet
under it. How to write them is in CLAUDE.md, and CodeRabbit reviews the
judgment part. `tests/test_page_metadata.py` checks the part that can be
counted:

- Every page declares a `title` and a `description`. Without a title Mintlify
  falls back to the file name.
- A title is at most 60 characters, where Google cuts it even without the
  suffix, and no two pages share one. CLAUDE.md asks for about 40.
- `<TechArticleSchema>` repeats the title, the description and the page's
  path exactly. It adds a second structured-data block beside the one
  Mintlify builds from the frontmatter, so a retitle has to change both
  copies, or Google reads two different headlines for one page.

The pages under `v3/expert-models/features/` take theirs from
`scripts/generate_features.py`, so a fix to one of them goes in the
generator. `tests/test_generate_features.py` covers how it writes a
description (whole sentences only) and the redirect it adds to `docs.json`
when the API drops a feature, so the old URL does not 404.

## Configuration blocks

The integration pages hand a reader a file to paste into some other program:
Continue, Kilo Code, LibreChat, Codex CLI, OpenCode. There is no code to run,
so no snippet runner covers them. `tests/test_config_blocks.py` covers the
JSON, YAML and TOML blocks under `v3/integrations/` instead, and checks the
three things that can be wrong with a config:

- **It parses** as the language its fence declares, so pasting it does not
  break the file it goes in.
- **Every model it names is one Eden AI serves.** The catalog is the union of
  seven routes, because `/v3/models` is hardcoded to the chat endpoints and
  lists chat models only. A config that sets an embeddings model alongside its
  chat models would be called broken by `/v3/models` alone.
- **Every Eden AI URL points at something.** A base URL is checked by asking
  for `/models` underneath it, since a base URL on its own answers 404 by
  design and always will.

This runs on every pull request rather than weekly, unlike the third-party
links. The split is about whose site has to be up: the model catalog is Eden
AI's own public API, needs no credential, and a model id going stale is worth
catching on the pull request that introduces it.

Working out what is a model id is most of the job here, and it is decided by
data rather than by a list. A config block is full of strings with a slash in
them that are not models: docker volume mounts, image tags, MIME types, URLs.
A shape rule drops what cannot be an id at all, and then only what begins with
a provider the catalog actually lists is treated as a model. That is why
`image/gif` is not a model reference and nothing had to say so.

A block that is not a whole file, a menu of alternative values for one key or
a single line of a larger document, carries the same
`{/* skip-test: reason */}` marker every other runner honours. The names
inside it are still checked, because a menu of models goes stale like any
other. `nginx` blocks are out of scope: no parser reads them and they name no
models.

## Integration pages

A config that parses can still point its tool at Eden AI in a way the tool
cannot use. Claude Code speaks the Anthropic Messages API and sends its key as
`x-api-key`, Codex speaks the Responses API, and every coding agent attaches
its tool definitions to every request, so a model that cannot take tools fails
on the first message. None of that is on the page, and none of it was tested.
Two modules cover it.

`tests/integrations.py` reads what each page points its tool at, from the page
itself: every model it names (config blocks, shell exports, table cells,
prose) and every setting that holds a model. The one fact it
cannot read is which protocol the tool speaks, so `TOOLS` there holds one line
per page saying so, and whether the tool sends tool definitions. A new
integration page fails until it has an entry.

`tests/test_integrations.py` checks, cheapest first:

- **Without credentials**, every model the page names outside a config block
  is one Eden AI serves (`test_config_blocks.py` covers the ones inside), every
  setting that holds a model names a whole `provider/model` id, and an agent
  is only pointed at models whose catalog entry says they support function
  calling. A setting is any key or variable ending in `model` or `models`, or
  qualified after the word (`TASK_MODEL_EXTERNAL`), and a list holds a setting
  per model: `RAG_EMBEDDING_MODEL=text-embedding-3-small` is invisible to a
  scan for `provider/model` strings, and the tool sends the value as it stands.
- **With the sandbox token**, the request each page's tool sends: its
  protocol, its auth and the page's lead model, streamed, with tool
  definitions for an agent. One per page and kind of call, which costs nothing.
- **With the production token**, on the weekly run, every model the pages
  name through the protocol of every tool naming it, deduplicated across
  pages. For an agent this is the whole tool loop: a real model is given a
  task that needs the tool, handed the result, and has to answer with a random
  word only the result contains.

`tests/test_integration_clis.py` runs the real Claude Code, Codex and OpenCode
CLIs, installed from `tests/clis/package.json`, with the settings their pages give
them: the export lines, the `config.toml` block, the script that generates
`opencode.json`. Each runs in a home directory of its own with a bare
environment, so a credential on the machine cannot make it pass by reaching
the vendor. Codex runs with `--strict-config`, so a key the page sets that the
pinned Codex no longer recognises fails. The sandbox run is on every pull
request. The real-model run, on the weekly one, asks what a file says, so the
agent has to use its own file-reading tool through Eden AI.

Two things make a real-model task fail for reasons that are not Eden AI's, and
both are handled in the tests rather than worked around per model:

- Every request sets a cap on the answer. Without one the API reserves the
  model's whole output ceiling against the key's spending limit first, and a
  key with a limit is refused with `402` for a request costing a fraction of a
  cent.
- The tasks are dull on purpose, and the tool call is asked for rather than
  forced. "Read this file and repeat it exactly" reads like exfiltration to a
  provider's safety classifier, and Claude Opus refuses it; the newest Claude
  models also refuse a forced `tool_choice`, which no agent sends anyway.

## CI (GitHub Actions)

The workflow at `.github/workflows/test-snippets.yml` runs on PRs that touch `v3/**/*.mdx`, `docs.json`, `snippets/**`, `tests/**` or `scripts/**`:

1. **Check snippet syntax**: parses every extracted snippet, Python, shell and JavaScript, and type-checks the TypeScript ones. No credentials and no API calls, so it still reports a broken snippet on a run where the secrets are missing. It needs the npm packages, which is why `npm ci` runs before it
2. **Check documentation links**: follows every link on every page, and fetches the two OpenAPI specs the API reference tabs render from. No credentials
3. **Check page titles and descriptions**: every page's title and description, the copy its structured data keeps, and the feature page generator. No credentials and no requests
4. **Check integration configuration and pages**: parses the JSON, YAML and TOML config on the integration pages and checks every model and URL it names against the live catalog, then every other model and model setting on those pages, and the function-calling capability of the models the agents are pointed at. No credentials, and one process, because starting xdist workers takes longer than the assertions
5. **Run Python snippets**, **Run shell snippets** and **Run JS and TS snippets**: execution tests with the `EDEN_AI_SANDBOX_TOKEN`, `EDEN_AI_PRODUCTION_TOKEN` and `EDEN_AI_MANAGEMENT_KEY` secrets
6. **Run integration requests and CLIs**: each integration page's request sent the way its tool sends it, and the real Claude Code, Codex and OpenCode CLIs run with the page's settings. Sandbox on a pull request, real models weekly

It also runs weekly, Mondays at 06:00 UTC against `main`, because the docs go
stale against a moving API even when nobody edits them. The weekly run is the
only scheduled one that sets `EDEN_AI_RUN_PAID_CALLS` and
`EDEN_AI_CHECK_EXTERNAL_LINKS`, so the `paid-test` samples and the third-party
links get their coverage there rather than on every pull request. A manual
dispatch sets both too.

Installs from `requirements-lock.txt`, `tests/package-lock.json` and `tests/clis/package-lock.json` for reproducible builds.

To set up: add `EDEN_AI_SANDBOX_TOKEN`, `EDEN_AI_PRODUCTION_TOKEN` and `EDEN_AI_MANAGEMENT_KEY` as repository secrets in GitHub. Without `EDEN_AI_MANAGEMENT_KEY` the Management API samples are reported as skipped, not failed.

## Common Failure Patterns

| Pattern | Cause | Fix |
|---------|-------|-----|
| `IndentationError: expected an indented block` | Code inside a function not indented in the `.mdx` | Add 4-space indent to the code block in the `.mdx` |
| `SyntaxError` with `**name**` | Markdown bold rendering corrupted `__name__` | Use `__name__` (double underscores) inside code fences |
| `SyntaxError` with `\*\*` | Markdown escaped `**` operator | Use `**` (unescaped) inside code fences |
| `unexpected indent` on first line | Extra indentation in the `.mdx` code block | Remove leading whitespace from the code block |
