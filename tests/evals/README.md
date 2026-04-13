# Mintlify Ask AI — Evaluation Pipeline

Evaluation pipeline for the [docs.edenai.co](https://docs.edenai.co) "Ask AI" feature, using [deepeval](https://github.com/confident-ai/deepeval) with Eden AI as the judge LLM.

## What it evaluates

| Metric | What it measures | Low score means | Actionable fix |
|--------|-----------------|-----------------|----------------|
| **Retrieval Accuracy** | Did Mintlify find the right doc page(s)? | Page is hard to discover | Improve page titles, headings, metadata |
| **Answer Relevancy** | Does the answer address the question? | Answer drifts off-topic or admits ignorance | Improve doc structure/discoverability |
| **Contextual Recall** | Does the doc contain info for the expected answer? | Documentation has a coverage gap | Add missing content to the doc |

**Key principle:** We control the docs, not the AI model. All metrics produce actionable signals — failures point to documentation improvements, not AI tuning.

## Setup

Uses the shared repo-root venv. Eval-specific deps (`deepeval`, `httpx`) are listed in `tests/requirements.txt`.

```bash
# From repo root (if venv not set up yet)
uv venv .venv
source .venv/bin/activate
uv pip install -r tests/requirements.txt
```

Add the eval keys to the shared `tests/.env` (see `tests/.env.example` for the full template):

```bash
cp tests/.env.example tests/.env
# then fill in EDENAI_TOKEN and MINTLIFY_API_KEY
```

Required environment variables:
- `EDEN_AI_PRODUCTION_API_TOKEN` — Eden AI production key (reused from snippet tests, powers the LLM judge)
- `MINTLIFY_API_KEY` — Mintlify API key (`mint_dsc_...` format, needed for first run or `--refresh-answers`)

Optional:
- `EVAL_JUDGE_MODEL` — Override the judge model (default: `openai/gpt-4o`)

## Running

```bash
# Run all evals (use -n0 to disable xdist from tests/pytest.ini)
pytest tests/evals/ -n0

# Run a specific metric
pytest tests/evals/test_retrieval_accuracy.py -n0
pytest tests/evals/test_answer_relevancy.py -n0
pytest tests/evals/test_coverage_gaps.py -n0

# Run for a specific question
pytest tests/evals/ -n0 -k q01

# Re-fetch Ask AI answers (ignoring cache)
pytest tests/evals/ -n0 --refresh-answers
```

### Filtering by category or difficulty

```bash
# By category
pytest tests/evals/ -n0 --category=llm
pytest tests/evals/ -n0 --category=cross-cutting

# By difficulty
pytest tests/evals/ -n0 --difficulty=basic
pytest tests/evals/ -n0 --difficulty=advanced
```

> **Note:** `-n0` disables pytest-xdist parallelism (configured in `tests/pytest.ini`).
> Evals use session-scoped fixtures for answer caching which require single-process mode.

## Answer caching

Mintlify Ask AI responses (answer text + retrieved page paths) are cached to `tests/evals/.cache/answers.json` after the first run. Subsequent runs reuse the cache to allow fast iteration on metrics and thresholds without hitting the Mintlify API.

Use `--refresh-answers` to force a re-fetch.

If the cache exists, `MINTLIFY_API_KEY` is not required.

## Adding new questions

Edit `dataset.json` and add a new entry:

```json
{
    "id": "q22",
    "question": "Your question here?",
    "expected_output": "A concise ideal answer for contextual recall evaluation.",
    "source_doc": "v3/path/to/relevant-doc.mdx",
    "category": "llm",
    "difficulty": "intermediate"
}
```

For cross-page questions, use an array for `source_doc`:

```json
{
    "id": "q23",
    "question": "How do X and Y compare?",
    "expected_output": "...",
    "source_doc": ["v3/path/to/x.mdx", "v3/path/to/y.mdx"],
    "category": "cross-cutting",
    "difficulty": "advanced"
}
```

Then run `pytest tests/evals/ -n0 --refresh-answers -k q22` to fetch the answer and evaluate it.

## Dataset dimensions

- **21 questions** across 5 categories and 3 difficulty levels
- **Categories**: `llm`, `expert-models`, `integrations`, `general`, `cross-cutting`
- **Difficulty**: `basic` (single page), `intermediate` (requires context), `advanced` (cross-page synthesis)

## Project structure

| File | Purpose |
|------|---------|
| `dataset.json` | Test questions with expected outputs, source docs, and metadata |
| `conftest.py` | Pytest fixtures (LLM, answer caching, doc contexts, filtering) |
| `edenai_llm.py` | Eden AI adapter for deepeval's LLM judge interface |
| `mintlify_client.py` | Mintlify Ask AI SSE client (captures answer + retrieved pages) |
| `context_loader.py` | Reads .mdx docs as retrieval context |
| `test_retrieval_accuracy.py` | Retrieval accuracy (did Mintlify find the right page?) |
| `test_answer_relevancy.py` | Answer relevancy metric (on-topic?) |
| `test_coverage_gaps.py` | Contextual recall metric (docs have enough info?) |
