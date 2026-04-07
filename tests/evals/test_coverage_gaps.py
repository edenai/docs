"""Coverage gap detection: does the documentation contain enough information?

Two complementary metrics:

1. ContextualRecall — compares the expected answer against the source doc.
   A low score means the doc is missing information needed for a complete answer.

2. DocCompleteness (custom GEval) — LLM-judged assessment of whether the doc
   content is sufficient to fully answer the question.
"""

from __future__ import annotations

from deepeval import assert_test
from deepeval.metrics import ContextualRecallMetric, GEval
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
            "contains all the information needed to completely and accurately "
            "answer the input question. Consider: Are relevant API endpoints "
            "documented? Are code examples provided? Are parameters and their "
            "types explained? Is the authentication method shown?"
        ),
        evaluation_steps=[
            "Identify all key information points needed to answer the question",
            "Check if each information point is present in the retrieval_context",
            "Assess whether code examples in the context are complete and correct",
            "Score 1-5: 5 = all info present, 1 = critical information missing",
        ],
        model=model,
        threshold=0.6,
    )


def test_contextual_recall(entry, edenai_llm, mintlify_answers, doc_contexts):
    test_case = LLMTestCase(
        input=entry["question"],
        actual_output=mintlify_answers[entry["id"]],
        expected_output=entry["expected_output"],
        retrieval_context=doc_contexts[entry["id"]],
    )
    metric = ContextualRecallMetric(threshold=0.7, model=edenai_llm)
    assert_test(test_case, [metric])


def test_doc_completeness(entry, edenai_llm, mintlify_answers, doc_contexts):
    test_case = LLMTestCase(
        input=entry["question"],
        actual_output=mintlify_answers[entry["id"]],
        retrieval_context=doc_contexts[entry["id"]],
    )
    metric = _doc_completeness_metric(edenai_llm)
    assert_test(test_case, [metric])
