# Mintlify Ask AI — DeepEval Evaluation Pipeline

LLM-as-a-judge evaluation pipeline for the [docs.edenai.co](https://docs.edenai.co) "Ask AI" feature, using [deepeval](https://github.com/confident-ai/deepeval) with Eden AI as the judge LLM.

## What it evaluates

| Metric | What it measures | Low score means |
|--------|-----------------|-----------------|
| **Faithfulness** | Is the answer grounded in the source doc? | Ask AI is hallucinating beyond what docs say |
| **Answer Relevancy** | Does the answer address the question? | Answer drifts off-topic |
| **Contextual Recall** | Does the doc contain info for the expected answer? | Documentation has a coverage gap |
| **Doc Completeness** | Is the doc sufficient to fully answer the question? | Docs need more content for this topic |

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
- `MINTLIFY_API_KEY` — Mintlify API key (`mint_dsc_...` format, needed for first run)

Optional:
- `EVAL_JUDGE_MODEL` — Override the judge model (default: `openai/gpt-4o`)

## Running

```bash
# Run all evals (use -n0 to disable xdist from tests/pytest.ini)
pytest tests/evals/ -n0

# Run a specific metric
pytest tests/evals/test_faithfulness.py -n0
pytest tests/evals/test_answer_relevancy.py -n0
pytest tests/evals/test_coverage_gaps.py -n0

# Run for a specific question
pytest tests/evals/ -n0 -k q1

# Re-fetch Ask AI answers (ignoring cache)
pytest tests/evals/ -n0 --refresh-answers
```

> **Note:** `-n0` disables pytest-xdist parallelism (configured in `tests/pytest.ini`).
> Evals use session-scoped fixtures for answer caching which require single-process mode.

## Answer caching

Mintlify Ask AI responses are cached to `tests/evals/.cache/answers.json` after the first run. Subsequent runs reuse the cache to allow fast iteration on metrics and thresholds without hitting the Mintlify API.

Use `--refresh-answers` to force a re-fetch.

If the cache exists, `MINTLIFY_API_KEY` is not required.

## Adding new questions

Edit `dataset.json` and add a new entry:

```json
{
    "id": "q13",
    "question": "Your question here?",
    "expected_output": "A concise ideal answer for contextual recall evaluation.",
    "source_doc": "v3/path/to/relevant-doc.mdx",
    "category": "llm"
}
```

Then run `pytest tests/evals/ -n0 --refresh-answers -k q13` to fetch the answer and evaluate it.

## Project structure

| File | Purpose |
|------|---------|
| `edenai_llm.py` | Eden AI adapter for deepeval's LLM judge interface |
| `mintlify_client.py` | Mintlify Ask AI SSE client |
| `context_loader.py` | Reads .mdx docs as retrieval context |
| `dataset.json` | Test questions with expected outputs and source doc paths |
| `conftest.py` | Pytest fixtures (LLM, answer caching, doc contexts) |
| `test_faithfulness.py` | Faithfulness metric tests |
| `test_answer_relevancy.py` | Answer relevancy metric tests |
| `test_coverage_gaps.py` | Contextual recall + doc completeness tests |
