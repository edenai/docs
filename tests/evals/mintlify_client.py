"""Mintlify Ask AI client.

Sends questions to the Mintlify discovery v2 assistant endpoint and
parses the SSE streaming response into plain text.
"""

from __future__ import annotations

import json
import uuid

import httpx

MINTLIFY_ASSISTANT_URL = (
    "https://api.mintlify.com/discovery/v2/assistant/{domain}/message"
)


def ask_mintlify(
    question: str,
    api_key: str,
    domain: str = "docs.edenai.co",
    client: httpx.Client | None = None,
    retries: int = 3,
    retrieval_page_size: int = 10,
    version_filter: str = "V3",
) -> str:
    """Send a question to Mintlify Ask AI and return the answer text.

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

    def _post(c: httpx.Client) -> str:
        resp = c.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        return _parse_streaming_response(resp.text)

    for attempt in range(1 + retries):
        if client is None:
            with httpx.Client(timeout=60) as c:
                answer = _post(c)
        else:
            answer = _post(client)

        if answer or attempt == retries:
            return answer


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

    return "".join(parts)
