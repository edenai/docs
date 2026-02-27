#!/usr/bin/env python3
"""
Mintlify Ask AI — Quality Assurance Validation Script

Sends each question from dataset.json to the Mintlify Ask AI API,
then uses Claude as an LLM-as-judge to score answer quality.
Optionally runs extracted code snippets against the Eden AI API.

Usage:
    python validate.py
    python validate.py --skip-code-exec
    python validate.py --question q1

Environment variables:
    MINTLIFY_API_KEY   - Mintlify API key (mint_dsc_...)
    EDEN_AI_API_KEY    - Eden AI API key (used for both LLM judge and code execution)
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import textwrap
from datetime import datetime, timezone
from pathlib import Path

import httpx

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MINTLIFY_ASSISTANT_URL = (
    "https://api.mintlify.com/discovery/v2/assistant/{domain}/message"
)
MINTLIFY_DOMAIN = "docs.edenai.co"
EDENAI_LLM_URL = "https://api.edenai.run/v3/llm/chat/completions"
DATASET_PATH = Path(__file__).parent / "dataset.json"
REPORT_PATH = Path(__file__).parent / "report.json"

JUDGE_MODEL = "anthropic/claude-sonnet-4-5"
JUDGE_MAX_TOKENS = 1024


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def load_dataset(path: Path) -> list[dict]:
    with open(path) as f:
        return json.load(f)


def env_or_die(name: str) -> str:
    val = os.environ.get(name)
    if not val:
        print(f"ERROR: environment variable {name} is not set.", file=sys.stderr)
        sys.exit(1)
    return val


# ---------------------------------------------------------------------------
# Mintlify Ask AI interaction
# ---------------------------------------------------------------------------


def mintlify_ask(question: str, api_key: str, domain: str = MINTLIFY_DOMAIN) -> str:
    """Send a question to Mintlify Ask AI (v2) and return the answer text.

    Uses the discovery v2 assistant endpoint:
    POST /discovery/v2/assistant/{domain}/message
    """
    url = MINTLIFY_ASSISTANT_URL.format(domain=domain)
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "fp": "qa-validation",
        "messages": [
            {
                "id": "msg-1",
                "role": "user",
                "parts": [{"type": "text", "text": question}],
            }
        ],
    }

    with httpx.Client(timeout=60) as client:
        resp = client.post(url, headers=headers, json=payload)
        resp.raise_for_status()

    return _parse_streaming_response(resp.text)


def _parse_streaming_response(raw: str) -> str:
    """Extract text content from Mintlify's SSE streaming response.

    Mintlify returns SSE events with these relevant types:
    - {"type":"text-delta","delta":"chunk"} — the actual answer text
    - {"type":"finish","finishReason":"stop"} — end of stream
    Other types (start, start-step, tool-input-*, tool-result, etc.) are ignored.
    """
    parts: list[str] = []

    for line in raw.splitlines():
        line = line.strip()
        if not line or not line.startswith("data: "):
            continue

        payload = line[6:]
        try:
            chunk = json.loads(payload)
        except json.JSONDecodeError:
            continue

        if not isinstance(chunk, dict):
            continue

        if chunk.get("type") == "text-delta":
            delta = chunk.get("delta", "")
            if delta:
                parts.append(delta)

    return "".join(parts)


# ---------------------------------------------------------------------------
# LLM-as-Judge (Claude via Eden AI)
# ---------------------------------------------------------------------------

JUDGE_PROMPT_TEMPLATE = textwrap.dedent("""\
    You are an expert evaluator for an AI documentation assistant.

    ## Task
    Rate the following answer on three dimensions (each 1-5):

    1. **Accuracy** — Does the answer contain correct information? Are API endpoints, parameters, and auth patterns correct?
    2. **Completeness** — Does the answer cover the key aspects the user asked about? Does it include code examples?
    3. **Code Correctness** — Are the code snippets syntactically correct and using the right API patterns?

    ## Question
    {question}

    ## Expected Answer Should Contain
    {expected_keywords}

    ## Expected Code Pattern
    {expected_code}

    ## Actual Answer from the AI Assistant
    {actual_answer}

    ## Instructions
    Respond with ONLY valid JSON (no markdown fences). Use this exact structure:
    {{
        "accuracy": <1-5>,
        "completeness": <1-5>,
        "code_correctness": <1-5>,
        "overall": <1-5>,
        "keyword_matches": ["list of expected keywords found in the answer"],
        "keyword_misses": ["list of expected keywords NOT found"],
        "issues": ["list of specific problems, if any"],
        "summary": "One-sentence assessment"
    }}
""")


def llm_judge(
    question: str,
    expected_keywords: list[str],
    expected_code: str,
    actual_answer: str,
    api_key: str,
) -> dict:
    """Use Claude (via Eden AI) to judge the quality of an answer."""
    prompt = JUDGE_PROMPT_TEMPLATE.format(
        question=question,
        expected_keywords=json.dumps(expected_keywords),
        expected_code=expected_code,
        actual_answer=actual_answer,
    )

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": JUDGE_MODEL,
        "max_tokens": JUDGE_MAX_TOKENS,
        "messages": [{"role": "user", "content": prompt}],
    }

    with httpx.Client(timeout=60) as client:
        resp = client.post(EDENAI_LLM_URL, headers=headers, json=payload)
        if resp.status_code != 200:
            raise RuntimeError(
                f"Eden AI LLM returned {resp.status_code}: {resp.text[:500]}"
            )

    resp_data = resp.json()

    # Extract content from OpenAI-compatible response
    try:
        result_text = resp_data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        raise RuntimeError(
            f"Unexpected Eden AI response structure: {json.dumps(resp_data)[:500]}"
        )

    # Strip markdown fences if the model added them despite instructions
    result_text = result_text.strip()
    result_text = re.sub(r"^```(?:json)?\s*\n?", "", result_text)
    result_text = re.sub(r"\n?\s*```$", "", result_text)
    result_text = result_text.strip()

    try:
        return json.loads(result_text)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"Judge returned invalid JSON: {e}\nRaw text: {result_text[:500]}"
        )


# ---------------------------------------------------------------------------
# Code execution validation
# ---------------------------------------------------------------------------


def extract_python_snippets(answer: str) -> list[str]:
    """Extract Python code blocks from the answer."""
    snippets = []
    for match in re.finditer(r"```python\s*\n(.*?)```", answer, re.DOTALL):
        code = match.group(1).strip()
        if code:
            snippets.append(code)
    return snippets


def make_code_executable(code: str, eden_api_key: str) -> str:
    """Replace placeholder API keys and cap max_tokens."""
    code = code.replace("YOUR_API_KEY", eden_api_key)
    code = code.replace("YOUR_EDEN_AI_API_KEY", eden_api_key)
    # Cap max_tokens to keep validation cheap
    code = re.sub(r'"max_tokens":\s*\d+', '"max_tokens": 10', code)
    return code


def run_python_snippet(code: str, eden_api_key: str) -> dict:
    """Run a Python snippet in a subprocess and return pass/fail + output."""
    executable_code = make_code_executable(code, eden_api_key)

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False
    ) as tmp:
        tmp.write(executable_code)
        tmp_path = tmp.name

    try:
        result = subprocess.run(
            [sys.executable, tmp_path],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return {
            "passed": result.returncode == 0,
            "stdout": result.stdout[:500],
            "stderr": result.stderr[:500],
        }
    except subprocess.TimeoutExpired:
        return {"passed": False, "stdout": "", "stderr": "Timeout after 30s"}
    finally:
        os.unlink(tmp_path)


# ---------------------------------------------------------------------------
# Main validation loop
# ---------------------------------------------------------------------------


def validate_one(
    entry: dict,
    mintlify_key: str,
    eden_key: str,
    skip_code_exec: bool,
    domain: str = MINTLIFY_DOMAIN,
) -> dict:
    """Validate a single Q&A entry. Returns a result dict."""
    qid = entry["id"]
    question = entry["question"]
    print(f"\n{'='*60}")
    print(f"[{qid}] {question}")
    print(f"{'='*60}")

    # 1. Get answer from Mintlify
    print("  -> Asking Mintlify...")
    try:
        actual_answer = mintlify_ask(question, mintlify_key, domain=domain)
        print(f"  -> Got answer ({len(actual_answer)} chars)")
    except Exception as e:
        print(f"  -> ERROR from Mintlify: {e}")
        return {
            "id": qid,
            "question": question,
            "status": "mintlify_error",
            "error": str(e),
        }

    # 2. LLM Judge
    print("  -> Judging with Claude...")
    try:
        judge_result = llm_judge(
            question=question,
            expected_keywords=entry["expected_answer_contains"],
            expected_code=entry["expected_code_snippet"],
            actual_answer=actual_answer,
            api_key=eden_key,
        )
        print(
            f"  -> Scores: accuracy={judge_result['accuracy']}, "
            f"completeness={judge_result['completeness']}, "
            f"code_correctness={judge_result['code_correctness']}, "
            f"overall={judge_result['overall']}"
        )
    except Exception as e:
        print(f"  -> ERROR from judge: {e}")
        judge_result = {"error": str(e)}

    # 3. Code execution (optional)
    code_results = []
    if not skip_code_exec and entry.get("has_executable_code"):
        snippets = extract_python_snippets(actual_answer)
        if snippets:
            print(f"  -> Running {len(snippets)} code snippet(s)...")
            for i, snippet in enumerate(snippets):
                result = run_python_snippet(snippet, eden_key)
                status = "PASS" if result["passed"] else "FAIL"
                print(f"     snippet {i+1}: {status}")
                if not result["passed"] and result["stderr"]:
                    print(f"     error: {result['stderr'][:200]}")
                code_results.append(result)
        else:
            print("  -> No Python snippets found to execute")

    return {
        "id": qid,
        "question": question,
        "category": entry.get("category", ""),
        "source_doc": entry.get("source_doc", ""),
        "status": "ok",
        "actual_answer_length": len(actual_answer),
        "actual_answer_preview": actual_answer[:300],
        "judge": judge_result,
        "code_execution": code_results,
    }


def print_summary(results: list[dict]) -> None:
    """Print a human-readable summary table."""
    print(f"\n\n{'='*70}")
    print("VALIDATION SUMMARY")
    print(f"{'='*70}")
    print(f"{'ID':<6} {'Category':<18} {'Acc':>4} {'Comp':>5} {'Code':>5} {'Overall':>8} {'Status'}")
    print(f"{'-'*6} {'-'*18} {'-'*4} {'-'*5} {'-'*5} {'-'*8} {'-'*10}")

    for r in results:
        if r["status"] != "ok":
            print(f"{r['id']:<6} {'':18} {'':>4} {'':>5} {'':>5} {'':>8} {r['status']}")
            continue

        j = r.get("judge", {})
        acc = j.get("accuracy", "?")
        comp = j.get("completeness", "?")
        code = j.get("code_correctness", "?")
        overall = j.get("overall", "?")
        cat = r.get("category", "")

        code_exec_status = ""
        if r["code_execution"]:
            passed = sum(1 for c in r["code_execution"] if c["passed"])
            total = len(r["code_execution"])
            code_exec_status = f" [exec: {passed}/{total}]"

        print(
            f"{r['id']:<6} {cat:<18} {acc:>4} {comp:>5} {code:>5} {overall:>8} "
            f"ok{code_exec_status}"
        )

    # Overall stats
    ok_results = [r for r in results if r["status"] == "ok"]
    if ok_results:
        avg_overall = sum(
            r["judge"].get("overall", 0) for r in ok_results
        ) / len(ok_results)
        print(f"\nAverage overall score: {avg_overall:.1f}/5")
        print(f"Questions evaluated: {len(ok_results)}/{len(results)}")


def main():
    parser = argparse.ArgumentParser(description="Validate Mintlify Ask AI quality")
    parser.add_argument(
        "--skip-code-exec",
        action="store_true",
        help="Skip code execution validation",
    )
    parser.add_argument(
        "--question",
        type=str,
        help="Run only a specific question ID (e.g., q1)",
    )
    parser.add_argument(
        "--dataset",
        type=str,
        default=str(DATASET_PATH),
        help="Path to dataset JSON file",
    )
    parser.add_argument(
        "--domain",
        type=str,
        default=MINTLIFY_DOMAIN,
        help=f"Mintlify docs domain (default: {MINTLIFY_DOMAIN})",
    )
    args = parser.parse_args()

    # Load env vars
    mintlify_key = env_or_die("MINTLIFY_API_KEY")
    eden_key = env_or_die("EDEN_AI_API_KEY")

    # Load dataset
    dataset = load_dataset(Path(args.dataset))
    print(f"Loaded {len(dataset)} questions from {args.dataset}")

    # Filter if --question specified
    if args.question:
        dataset = [e for e in dataset if e["id"] == args.question]
        if not dataset:
            print(f"ERROR: question '{args.question}' not found in dataset.")
            sys.exit(1)

    # Run validation
    results = []
    for entry in dataset:
        result = validate_one(
            entry,
            mintlify_key=mintlify_key,
            eden_key=eden_key,
            skip_code_exec=args.skip_code_exec,
            domain=args.domain,
        )
        results.append(result)

    # Print summary
    print_summary(results)

    # Save report
    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "questions_total": len(dataset),
        "questions_ok": sum(1 for r in results if r["status"] == "ok"),
        "results": results,
    }
    report_path = Path(args.dataset).parent / "report.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\nFull report saved to: {report_path}")


if __name__ == "__main__":
    main()
