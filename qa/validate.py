#!/usr/bin/env python3
"""
Mintlify Ask AI — Quality Assurance Validation Script

Sends each question from dataset.json to the Mintlify Ask AI API,
then uses an OpenAI Agents SDK agent (backed by Eden AI with GPT-4o) as
an LLM-as-judge to score answer quality and to execute extracted code
snippets with intelligent error analysis.

Usage:
    python validate.py
    python validate.py --skip-code-exec
    python validate.py --question q1
    python validate.py --no-agent          # subprocess fallback

Environment variables:
    MINTLIFY_API_KEY   - Mintlify API key (mint_dsc_...)
    EDEN_AI_API_KEY    - Eden AI API key (used for both LLM judge and code execution)
"""

import argparse
import asyncio
import json
import os
import re
import subprocess
import sys
import tempfile
import textwrap
from datetime import datetime, timezone
from pathlib import Path

from agents import Agent, RunConfig, Runner, function_tool
from agents.models.interface import Model, ModelProvider
from agents.models.multi_provider import MultiProvider, MultiProviderMap
from agents.models.openai_chatcompletions import OpenAIChatCompletionsModel
import httpx
from openai import AsyncOpenAI

# --------------------------
# Configuration
#---------------------------

MINTLIFY_ASSISTANT_URL = (
    "https://api.mintlify.com/discovery/v2/assistant/{domain}/message"
)
MINTLIFY_DOMAIN = "docs.edenai.co"
EDENAI_LLM_URL = "https://api.edenai.run/v3/llm/chat/completions"
DATASET_PATH = Path(__file__).parent / "dataset.json"
REPORT_PATH = Path(__file__).parent / "report.json"

# Eden AI model name in provider/model format
EDENAI_MODEL = "openai/gpt-4o"
# Prefixed for the Agents SDK — "edenai/" routes through our custom provider,
# which strips the prefix and sends "openai/gpt-4o" to Eden AI intact.
AGENT_MODEL = f"edenai/{EDENAI_MODEL}"

# ----------------------------------------------------
# OpenAI Agents SDK setup (Eden AI as LLM provider)
# ----------------------------------------------------


class EdenAIProvider(ModelProvider):
    """Routes requests to Eden AI, preserving the full provider/model string."""

    def __init__(self, client: AsyncOpenAI):
        self._client = client

    def get_model(self, model_name: str | None) -> Model:
        return OpenAIChatCompletionsModel(
            model=model_name or EDENAI_MODEL,
            openai_client=self._client,
        )


@function_tool
def execute_python(code: str) -> str:
    """Execute a Python code snippet and return the output.

    Any EDEN_AI_API_KEY placeholder in the code is replaced with
    the real key from the environment at execution time.
    """
    # Inject real API key only at execution time — never in the prompt
    eden_key = os.environ.get("EDEN_AI_API_KEY", "")
    code = code.replace("EDEN_AI_API_KEY", eden_key)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as tmp:
        tmp.write(code)
        tmp_path = tmp.name
    try:
        result = subprocess.run(
            [sys.executable, tmp_path],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            return f"SUCCESS\nOutput:\n{result.stdout[:1000]}"
        else:
            return (
                f"ERROR (exit code {result.returncode})\n"
                f"Stderr:\n{result.stderr[:1000]}\n"
                f"Stdout:\n{result.stdout[:500]}"
            )
    except subprocess.TimeoutExpired:
        return "ERROR: Execution timed out after 30 seconds"
    finally:
        os.unlink(tmp_path)


code_validator_agent = None
judge_agent = None
_run_config = None


def setup_agents(api_key: str):
    """Configure OpenAI Agents SDK client and create agents.

    Registers an "edenai" prefix in the SDK's MultiProvider so that model
    names like "edenai/openai/gpt-4o" are routed through our EdenAIProvider.
    The SDK strips the "edenai/" prefix and the provider sends "openai/gpt-4o"
    to Eden AI intact.
    """
    global code_validator_agent, judge_agent, _run_config

    client = AsyncOpenAI(
        base_url="https://api.edenai.run/v3/llm",
        api_key=api_key,
    )

    # Register "edenai" as a custom provider prefix
    provider_map = MultiProviderMap()
    provider_map.add_provider("edenai", EdenAIProvider(client))
    provider = MultiProvider(provider_map=provider_map)

    _run_config = RunConfig(
        model_provider=provider,
        tracing_disabled=True,
    )

    code_validator_agent = Agent(
        name="code-validator",
        instructions=(
            "You validate Python code snippets from AI documentation answers.\n\n"
            "You MUST use the execute_python tool to run the code. "
            "Do NOT simulate or guess the output.\n"
            "The EDEN_AI_API_KEY placeholder is replaced with the real key "
            "automatically at runtime — pass the code as-is.\n\n"
            "After execution, return ONLY valid JSON:\n"
            "{\n"
            '    "passed": true/false,\n'
            '    "output": "execution output or error",\n'
            '    "analysis": "brief explanation of what happened"\n'
            "}"
        ),
        tools=[execute_python],
        model=AGENT_MODEL,
    )

    judge_agent = Agent(
        name="judge",
        instructions=JUDGE_SYSTEM_PROMPT,
        model=AGENT_MODEL,
    )


# --------------
# Helpers
# --------------

def load_dataset(path: Path) -> list[dict]:
    with open(path) as f:
        return json.load(f)


def env_or_die(name: str) -> str:
    val = os.environ.get(name)
    if not val:
        print(f"ERROR: environment variable {name} is not set.", file=sys.stderr)
        sys.exit(1)
    return val


# ------------------------------
# Mintlify Ask AI interaction
# ------------------------------


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


# --------------------------------------------------------
# LLM-as-Judge (GPT-4o via Eden AI / OpenAI Agents SDK)
# --------------------------------------------------------

JUDGE_SYSTEM_PROMPT = textwrap.dedent("""\
    You are an expert evaluator for an AI documentation assistant.

    Rate answers on three dimensions (each 1-5):
    1. **Accuracy** — Correct information, API endpoints, parameters, auth patterns?
    2. **Completeness** — Covers key aspects? Includes code examples?
    3. **Code Correctness** — Syntactically correct snippets using right API patterns?

    Respond with ONLY valid JSON (no markdown fences). Use this exact structure:
    {
        "accuracy": <1-5>,
        "completeness": <1-5>,
        "code_correctness": <1-5>,
        "overall": <1-5>,
        "keyword_matches": ["list of expected keywords found in the answer"],
        "keyword_misses": ["list of expected keywords NOT found"],
        "issues": ["list of specific problems, if any"],
        "summary": "One-sentence assessment"
    }
""")

JUDGE_USER_TEMPLATE = textwrap.dedent("""\
    ## Question
    {question}

    ## Expected Answer Should Contain
    {expected_keywords}

    ## Expected Code Pattern
    {expected_code}

    ## Actual Answer from the AI Assistant
    {actual_answer}
""")


def _parse_json(text: str) -> dict:
    """Parse JSON from LLM output, stripping markdown fences if present."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*\n?", "", text)
    text = re.sub(r"\n?\s*```$", "", text)
    text = text.strip()
    return json.loads(text)


async def llm_judge_agent(
    question: str,
    expected_keywords: list[str],
    expected_code: str,
    actual_answer: str,
) -> dict:
    """Use GPT-4o (via OpenAI Agents SDK + Eden AI) to judge answer quality."""
    prompt = JUDGE_USER_TEMPLATE.format(
        question=question,
        expected_keywords=json.dumps(expected_keywords),
        expected_code=expected_code,
        actual_answer=actual_answer,
    )

    result = await Runner.run(judge_agent, prompt, run_config=_run_config)

    try:
        return _parse_json(result.final_output)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"Judge returned invalid JSON: {e}\n"
            f"Raw text: {result.final_output[:500]}"
        )


def llm_judge_http(
    question: str,
    expected_keywords: list[str],
    expected_code: str,
    actual_answer: str,
    api_key: str,
) -> dict:
    """Fallback: judge via direct HTTP to Eden AI (no agent SDK)."""
    system_msg = JUDGE_SYSTEM_PROMPT
    user_msg = JUDGE_USER_TEMPLATE.format(
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
        "model": EDENAI_MODEL,
        "max_tokens": 1024,
        "messages": [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ],
    }

    with httpx.Client(timeout=60) as client:
        resp = client.post(EDENAI_LLM_URL, headers=headers, json=payload)
        if resp.status_code != 200:
            raise RuntimeError(
                f"Eden AI LLM returned {resp.status_code}: {resp.text[:500]}"
            )

    resp_data = resp.json()
    try:
        result_text = resp_data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        raise RuntimeError(
            f"Unexpected Eden AI response structure: {json.dumps(resp_data)[:500]}"
        )

    try:
        return _parse_json(result_text)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"Judge returned invalid JSON: {e}\nRaw text: {result_text[:500]}"
        )


# --------------------------
# Code execution validation
# --------------------------


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


async def run_python_snippet_agent(code: str, eden_api_key: str) -> dict:
    """Use OpenAI Agents SDK to execute and analyze a code snippet."""
    # Replace placeholder keys with EDEN_AI_API_KEY (not the real value).
    # The execute_python tool injects the real key at execution time.
    safe_code = make_code_executable(code, "EDEN_AI_API_KEY")

    prompt = (
        "Execute this Python snippet using the execute_python tool "
        "and report results:\n\n"
        f"```python\n{safe_code}\n```"
    )

    try:
        result = await Runner.run(code_validator_agent, prompt, run_config=_run_config)
    except Exception as e:
        return {
            "passed": False,
            "stdout": "",
            "stderr": f"Agent error: {e}",
            "analysis": "",
        }

    # Parse agent's JSON response (strip markdown fences if present)
    try:
        parsed = _parse_json(result.final_output)
        return {
            "passed": parsed.get("passed", False),
            "stdout": parsed.get("output", "")[:500],
            "stderr": "",
            "analysis": parsed.get("analysis", ""),
        }
    except (json.JSONDecodeError, ValueError, AttributeError):
        return {
            "passed": False,
            "stdout": str(result.final_output)[:500],
            "stderr": "Agent returned non-JSON response",
            "analysis": "",
        }


# -----------------------
# Main validation loop
# -----------------------


async def validate_one(
    entry: dict,
    mintlify_key: str,
    eden_key: str,
    skip_code_exec: bool,
    use_agent: bool,
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
    print(f"  -> Judging with GPT-4o ({'agent' if use_agent else 'HTTP'})...")
    try:
        if use_agent:
            judge_result = await llm_judge_agent(
                question=question,
                expected_keywords=entry["expected_answer_contains"],
                expected_code=entry["expected_code_snippet"],
                actual_answer=actual_answer,
            )
        else:
            judge_result = llm_judge_http(
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
            mode = "agent" if use_agent else "subprocess"
            print(f"  -> Running {len(snippets)} code snippet(s) via {mode}...")
            for i, snippet in enumerate(snippets):
                if use_agent:
                    result = await run_python_snippet_agent(snippet, eden_key)
                else:
                    result = run_python_snippet(snippet, eden_key)
                status = "PASS" if result["passed"] else "FAIL"
                print(f"     snippet {i+1}: {status}")
                if not result["passed"] and result.get("stderr"):
                    print(f"     error: {result['stderr'][:200]}")
                if result.get("analysis"):
                    print(f"     analysis: {result['analysis'][:200]}")
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


async def async_main():
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
    parser.add_argument(
        "--no-agent",
        action="store_true",
        help="Use subprocess fallback instead of the OpenAI Agents SDK agent",
    )
    args = parser.parse_args()

    # Load env vars
    mintlify_key = env_or_die("MINTLIFY_API_KEY")
    eden_key = env_or_die("EDEN_AI_API_KEY")

    # Determine whether to use the agent
    use_agent = not args.no_agent
    if use_agent:
        setup_agents(eden_key)
        print("Agent mode: ON (OpenAI Agents SDK via Eden AI)")
    else:
        print("Agent mode: OFF (subprocess fallback)")

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
        result = await validate_one(
            entry,
            mintlify_key=mintlify_key,
            eden_key=eden_key,
            skip_code_exec=args.skip_code_exec,
            use_agent=use_agent,
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
        "agent_mode": use_agent,
        "results": results,
    }
    report_path = Path(args.dataset).parent / "report.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\nFull report saved to: {report_path}")


def main():
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
