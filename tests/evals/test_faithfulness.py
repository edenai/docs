"""Faithfulness evaluation: are Ask AI answers grounded in the source docs?

A low faithfulness score means the answer contains claims not supported by
the documentation — either hallucinated content or information from outside
the referenced source doc.
"""

from __future__ import annotations

from deepeval import assert_test
from deepeval.metrics import FaithfulnessMetric
from deepeval.test_case import LLMTestCase


def test_faithfulness(entry, edenai_llm, actual_output, doc_contexts):
    test_case = LLMTestCase(
        input=entry["question"],
        actual_output=actual_output,
        retrieval_context=doc_contexts[entry["id"]],
    )
    metric = FaithfulnessMetric(threshold=0.7, model=edenai_llm)
    assert_test(test_case, [metric])
