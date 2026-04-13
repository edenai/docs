"""Retrieval accuracy: did Mintlify find the right documentation page(s)?

A failure means Mintlify's search didn't return the expected source doc in
its retrieval results. This is actionable: improve page titles, headings,
or metadata to make the page more discoverable.

This metric is deterministic (no LLM judge) — it compares retrieved paths
against the source_doc field in the dataset.
"""

from __future__ import annotations


def _normalize_path(path: str) -> str:
    """Normalize a doc path for comparison.

    Strips leading/trailing slashes, removes .mdx extension, so that
    'v3/llms/chat-completions.mdx' matches 'v3/llms/chat-completions'.
    """
    return path.strip("/").removesuffix(".mdx")


def test_retrieval_accuracy(entry, retrieved_paths):
    source_doc = entry["source_doc"]
    if isinstance(source_doc, str):
        expected_paths = [source_doc]
    else:
        expected_paths = source_doc

    expected_normalized = {_normalize_path(p) for p in expected_paths}
    retrieved_normalized = [_normalize_path(p) for p in retrieved_paths]

    found = expected_normalized & set(retrieved_normalized)
    missing = expected_normalized - found

    assert not missing, (
        f"Mintlify did not retrieve expected page(s): {sorted(missing)}. "
        f"Retrieved: {retrieved_normalized}"
    )
