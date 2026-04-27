"""Mintlify Ask AI client.

Sends questions to the Mintlify discovery v2 assistant endpoint and
parses the SSE streaming response into plain text + retrieved page paths.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field

import httpx

MINTLIFY_ASSISTANT_URL = (
    "https://api.mintlify.com/discovery/v2/assistant/{domain}/message"
)


@dataclass
class MintlifyResponse:
    """Answer text and the doc pages Mintlify retrieved to build it."""

    answer: str = ""
    retrieved_paths: list[str] = field(default_factory=list)


def ask_mintlify(
    question: str,
    api_key: str,
    domain: str = "docs.edenai.co",
    client: httpx.Client | None = None,
    retries: int = 3,
    retrieval_page_size: int = 10,
    version_filter: str = "V3",
) -> MintlifyResponse:
    """Send a question to Mintlify Ask AI and return the answer + retrieved paths.

    Retries up to *retries* times if Mintlify returns an empty answer
    (which happens when it gets stuck in a tool-call loop).

    Parameters
    ----------
    retrieval_page_size:
        Number of search results Mintlify uses to build its answer.
        Higher values give the model more context (default 10,
        Mintlify default is 5).
    version_filter:
        Documentation version filter (default ``"V3"``).
    """
    url = MINTLIFY_ASSISTANT_URL.format(domain=domain)
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    msg_id = uuid.uuid4().hex[:16]
    payload: dict = {
        "fp": "qa-eval",
        "messages": [
            {
                "id": msg_id,
                "role": "user",
                "parts": [{"type": "text", "text": question}],
            }
        ],
        "retrievalPageSize": retrieval_page_size,
        "filter": {"version": version_filter},
    }

    def _post(c: httpx.Client) -> MintlifyResponse:
        resp = c.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        return _parse_streaming_response(resp.text)

    for attempt in range(1 + retries):
        if client is None:
            with httpx.Client(timeout=60) as c:
                result = _post(c)
        else:
            result = _post(client)

        if result.answer or attempt == retries:
            return result

    return MintlifyResponse()


def _parse_streaming_response(raw: str) -> MintlifyResponse:
    """Extract text content and retrieved paths from Mintlify's SSE stream.

    Mintlify returns SSE events with these relevant types:
    - {"type":"text-delta","delta":"chunk"} — the actual answer text
    - {"type":"tool-output-available","output":{"results":[...]}} — retrieved pages
    - {"type":"finish","finishReason":"stop"} — end of stream
    """
    parts: list[str] = []
    retrieved_paths: list[str] = []

    for line in raw.splitlines():
        line = line.strip()
        if not line or not line.startswith("data: "):
            continue

        data = line[6:]
        try:
            chunk = json.loads(data)
        except json.JSONDecodeError:
            continue

        if not isinstance(chunk, dict):
            continue

        if chunk.get("type") == "text-delta":
            delta = chunk.get("delta", "")
            if delta:
                parts.append(delta)
        elif chunk.get("type") == "tool-output-available":
            results = chunk.get("output", {}).get("results", [])
            for r in results:
                path = r.get("path", "")
                if path and path not in retrieved_paths:
                    retrieved_paths.append(path)

    return MintlifyResponse(answer="".join(parts), retrieved_paths=retrieved_paths)
