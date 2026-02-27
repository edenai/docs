# Mintlify Ask AI — Quality Assurance

Automated validation pipeline for the Eden AI docs "Ask AI" feature. Sends questions to the Mintlify Ask AI API, then uses **OpenAI Agents SDK** agents (backed by Eden AI with `openai/gpt-4o`) for both LLM-as-judge scoring and intelligent code execution with error analysis.

## Setup

```bash
pip install -r qa/requirements.txt
```

### Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `MINTLIFY_API_KEY` | Yes | Mintlify API key (`mint_dsc_...`) from the Mintlify dashboard |
| `EDEN_AI_API_KEY` | Yes | Eden AI API key — used for the LLM judge and running code snippets against Eden AI |

```bash
export MINTLIFY_API_KEY="mint_dsc_..."
export EDEN_AI_API_KEY="..."
```

## Usage

```bash
# Run full validation (agent mode — default)
python qa/validate.py

# Skip code execution tests
python qa/validate.py --skip-code-exec

# Validate a single question
python qa/validate.py --question q1

# Use subprocess fallback instead of the agent
python qa/validate.py --no-agent
```

### Agent mode vs subprocess fallback

By default the script uses the **OpenAI Agents SDK** (`openai-agents`) configured with Eden AI as the LLM provider, running `openai/gpt-4o` for everything:

- **Judge agent** — scores answer quality on accuracy, completeness, and code correctness
- **Code validator agent** — executes Python snippets via a custom `@function_tool`, analyzes errors intelligently (e.g., "failed because `openai` package not installed"), returns structured pass/fail with an `analysis` field

Pass `--no-agent` to fall back to direct HTTP calls for judging and plain subprocess for code execution (useful if Eden AI credits are low or for quick local testing).

## Output

The script prints a summary table to stdout and saves a detailed JSON report to `qa/report.json`.

### Summary table

```
ID     Category           Acc  Comp  Code  Overall Status
------ ------------------ ---- ----- ----- -------- ----------
q1     llm                  5     4     5        5 ok [exec: 1/1]
q2     universal-ai         4     4     3        4 ok
q3     authentication       5     5     5        5 ok [exec: 2/2]
q4     llm-streaming        4     3     4        4 ok
```

### Scoring dimensions (1-5)

- **Accuracy** — Are API endpoints, parameters, and auth patterns correct?
- **Completeness** — Does the answer cover the key aspects asked about?
- **Code Correctness** — Are code snippets syntactically correct and using the right patterns?
- **Overall** — Holistic quality score

## Adding new questions

Edit `qa/dataset.json` and add a new entry:

```json
{
    "id": "q5",
    "question": "How do I use Smart Routing with Eden AI?",
    "expected_answer_contains": [
        "smart routing",
        "/v3/llm/chat/completions",
        "edenai/smart-routing"
    ],
    "expected_code_snippet": "\"model\": \"edenai/smart-routing\"",
    "source_doc": "v3/how-to/llm/smart-routing.mdx",
    "category": "smart-routing",
    "has_executable_code": true
}
```

### Field reference

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique identifier (e.g., `q5`) |
| `question` | string | The question to ask the AI |
| `expected_answer_contains` | string[] | Keywords/phrases the answer should include |
| `expected_code_snippet` | string | A code pattern expected in the answer |
| `source_doc` | string | The docs page that should be the primary source |
| `category` | string | Category label for grouping in reports |
| `has_executable_code` | boolean | Whether to attempt running extracted Python snippets |

## Files

| File | Description |
|------|-------------|
| `dataset.json` | Q&A test cases |
| `validate.py` | Validation script |
| `requirements.txt` | Python dependencies |
| `report.json` | Generated report (gitignored) |
