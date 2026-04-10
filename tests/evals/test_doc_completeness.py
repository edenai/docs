"""Doc completeness evaluation: is the documentation sufficient?

A low score means the documentation page exists but lacks depth --
missing code examples, parameter docs, edge case coverage, or cross-references.
"""

from __future__ import annotations

from deepeval import assert_test
from deepeval.metrics import GEval
from deepeval.test_case import LLMTestCase, LLMTestCaseParams


def _doc_completeness_metric(model) -> GEval:
    return GEval(
        name="DocCompleteness",
        evaluation_params=[
            LLMTestCaseParams.INPUT,
            LLMTestCaseParams.ACTUAL_OUTPUT,
            LLMTestCaseParams.RETRIEVAL_CONTEXT,
        ],
        criteria=(
            "Evaluate whether the retrieval_context (documentation content) "
            "contains ALL information needed to completely and accurately "
            "answer the input question. Consider completeness across these "
            "dimensions: (1) Are the relevant API endpoints, URLs, and HTTP "
            "methods documented? (2) Are request parameters, their types, "
            "defaults, and constraints explained? (3) Are working code examples "
            "provided in at least one language? (4) Are edge cases and "
            "limitations stated (e.g., provider-specific behavior, feature "
            "availability boundaries, streaming-only-for-LLMs)? "
            "(5) Is authentication usage demonstrated? (6) Are related features "
            "cross-referenced (e.g., fallback mentioned on streaming page, "
            "webhooks mentioned on async page)?"
        ),
        evaluation_steps=[
            "Identify every information point needed to fully answer the question.",
            "For each point, check if it is present in the retrieval_context.",
            "Assess whether code examples are complete (imports, request, response "
            "handling) and syntactically correct.",
            "Check if provider-specific caveats or feature boundaries are stated.",
            "Check if related features are cross-referenced.",
            "Score on a 1-5 scale: 5 = all dimensions covered, 4 = minor gaps, "
            "3 = one significant dimension missing, 2 = multiple dimensions missing, "
            "1 = critical information absent.",
        ],
        model=model,
        threshold=0.6,
    )


def test_doc_completeness(entry, edenai_llm, actual_output, doc_contexts):
    test_case = LLMTestCase(
        input=entry["question"],
        actual_output=actual_output,
        retrieval_context=doc_contexts[entry["id"]],
    )
    metric = _doc_completeness_metric(edenai_llm)
    assert_test(test_case, [metric])
