"""Answer relevancy evaluation: does the Ask AI answer address the question?

A low relevancy score means the answer drifts off-topic or fails to address
what was actually asked.
"""

from __future__ import annotations

from deepeval import assert_test
from deepeval.metrics import AnswerRelevancyMetric
from deepeval.test_case import LLMTestCase


def test_answer_relevancy(entry, edenai_llm, mintlify_answers):
    test_case = LLMTestCase(
        input=entry["question"],
        actual_output=mintlify_answers[entry["id"]],
    )
    metric = AnswerRelevancyMetric(threshold=0.7, model=edenai_llm)
    assert_test(test_case, [metric])
