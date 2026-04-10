"""Coverage gap detection: does the documentation contain enough information?

ContextualRecall compares the expected answer against the source doc.
A low score means the doc is missing information needed for a complete answer.
"""

from __future__ import annotations

from deepeval import assert_test
from deepeval.metrics import ContextualRecallMetric
from deepeval.test_case import LLMTestCase


def test_contextual_recall(entry, edenai_llm, actual_output, doc_contexts):
    test_case = LLMTestCase(
        input=entry["question"],
        actual_output=actual_output,
        expected_output=entry["expected_output"],
        retrieval_context=doc_contexts[entry["id"]],
    )
    metric = ContextualRecallMetric(threshold=0.7, model=edenai_llm)
    assert_test(test_case, [metric])
