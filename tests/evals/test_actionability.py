"""Actionability evaluation: can a developer DO the thing from the answer?

A low score means the answer is conceptually correct but lacks enough
detail for implementation -- missing code, unclear parameter formats,
no response parsing, or no setup steps.
"""

from __future__ import annotations

from deepeval import assert_test
from deepeval.metrics import GEval
from deepeval.test_case import LLMTestCase, LLMTestCaseParams


def _actionability_metric(model) -> GEval:
    return GEval(
        name="Actionability",
        evaluation_params=[
            LLMTestCaseParams.INPUT,
            LLMTestCaseParams.ACTUAL_OUTPUT,
        ],
        criteria=(
            "Evaluate whether a developer could successfully implement the task "
            "described in the input question using ONLY the information in the "
            "actual_output. Consider: (1) Is the correct API endpoint and HTTP "
            "method provided? (2) Is the request format clear (JSON body structure, "
            "required fields, authentication header)? (3) Is a code example provided "
            "that could be copied and adapted with minimal changes? (4) Is the "
            "response format explained so the developer knows how to parse the "
            "result? (5) Are format strings unambiguous (e.g., model parameter "
            "format explicitly stated as provider/model or feature/subfeature/provider)? "
            "(6) Are prerequisite steps mentioned (install SDK, get API key, upload "
            "file first)? (7) Could a developer with no prior Eden AI knowledge "
            "follow these instructions end-to-end?"
        ),
        evaluation_steps=[
            "Read the question and determine what the user wants to accomplish.",
            "Examine the actual_output for a complete implementation path.",
            "Check for: endpoint URL, HTTP method, auth header, request body format.",
            "Check if code is provided and syntactically plausible.",
            "Check if response parsing is shown.",
            "Check if prerequisite steps or setup are mentioned.",
            "Score 1-5: 5 = immediately actionable end-to-end, 4 = minor gaps, "
            "3 = significant setup/parsing info missing, 2 = mostly conceptual without "
            "actionable details, 1 = too vague to act on.",
        ],
        model=model,
        threshold=0.6,
    )


def test_actionability(entry, edenai_llm, actual_output):
    test_case = LLMTestCase(
        input=entry["question"],
        actual_output=actual_output,
    )
    metric = _actionability_metric(edenai_llm)
    assert_test(test_case, [metric])
