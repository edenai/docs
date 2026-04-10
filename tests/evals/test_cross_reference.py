"""Cross-reference accuracy: correct synthesis across multiple doc pages?

Only runs for questions that reference multiple source documents.
A low score means the answer incorrectly merges concepts, conflates
different endpoints, or introduces contradictions between features.
"""

from __future__ import annotations

import pytest
from deepeval import assert_test
from deepeval.metrics import GEval
from deepeval.test_case import LLMTestCase, LLMTestCaseParams


def _cross_reference_accuracy_metric(model) -> GEval:
    return GEval(
        name="CrossReferenceAccuracy",
        evaluation_params=[
            LLMTestCaseParams.INPUT,
            LLMTestCaseParams.ACTUAL_OUTPUT,
            LLMTestCaseParams.RETRIEVAL_CONTEXT,
            LLMTestCaseParams.EXPECTED_OUTPUT,
        ],
        criteria=(
            "Evaluate whether the actual_output correctly synthesizes information "
            "from MULTIPLE documentation pages without introducing contradictions, "
            "conflating different features, or misattributing behavior from one "
            "endpoint to another. Consider: (1) Are differences between LLM and "
            "expert model endpoints correctly distinguished? (2) Are model string "
            "formats (provider/model vs feature/subfeature/provider) used correctly "
            "for the right endpoint? (3) Are feature boundaries accurately stated "
            "(e.g., streaming is LLM-only, webhooks are expert-model-only)? "
            "(4) When combining features (e.g., fallback + BYOK, streaming + "
            "structured output), are the interactions described correctly per the "
            "documentation? (5) Does the answer avoid conflating terminology "
            "(e.g., 'async' meaning expert-model async jobs vs general async "
            "programming)?"
        ),
        evaluation_steps=[
            "Identify which documentation topics the question spans.",
            "Check if the answer correctly attributes information to the right "
            "endpoint/feature.",
            "Look for any contradictions between claims made about different features.",
            "Verify model string formats are used correctly for each endpoint mentioned.",
            "Check if feature boundaries (LLM-only, expert-model-only) are stated "
            "correctly.",
            "Compare against the expected_output for factual consistency.",
            "Score 1-5: 5 = perfect synthesis with no conflation, 4 = minor "
            "imprecision, 3 = one significant conflation or misattribution, "
            "2 = multiple errors in synthesis, 1 = fundamentally confuses the "
            "features being compared.",
        ],
        model=model,
        threshold=0.6,
    )


def test_cross_reference_accuracy(entry, edenai_llm, actual_output, doc_contexts):
    if not isinstance(entry["source_doc"], list) or len(entry["source_doc"]) < 2:
        pytest.skip("Single-page question, cross-reference metric not applicable")

    test_case = LLMTestCase(
        input=entry["question"],
        actual_output=actual_output,
        expected_output=entry["expected_output"],
        retrieval_context=doc_contexts[entry["id"]],
    )
    metric = _cross_reference_accuracy_metric(edenai_llm)
    assert_test(test_case, [metric])
