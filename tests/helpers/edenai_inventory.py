import os
from functools import cache

import requests

_LLM_MODELS_ENDPOINT = "/v3/models"
_INFO_ENDPOINT = "/v3/info"
_EMBEDDINGS_ENDPOINT = "/v3/embeddings"

_EMBEDDING_PROBE_CANDIDATES = frozenset(
    {
        "openai/text-embedding-3-small",
        "openai/text-embedding-3-large",
        "openai/text-embedding-ada-002",
        "mistral/mistral-embed",
        "cohere/embed-english-v3.0",
        "cohere/embed-multilingual-v3.0",
    }
)


def _base_url() -> str:
    return os.environ.get("EDEN_AI_BASE_URL", "https://api.edenai.run")


def _auth_headers() -> dict[str, str]:
    token = os.environ.get("EDEN_AI_SANDBOX_API_TOKEN")
    if not token:
        raise RuntimeError(
            "EDEN_AI_SANDBOX_API_TOKEN is required to fetch Eden AI model inventory"
        )
    return {"Authorization": f"Bearer {token}"}


@cache
def get_model_inventory() -> frozenset[str]:
    base = _base_url()
    headers = _auth_headers()

    llm_resp = requests.get(f"{base}{_LLM_MODELS_ENDPOINT}", headers=headers, timeout=30)
    llm_resp.raise_for_status()
    llm_entries = llm_resp.json().get("data") or []
    llm_models = {
        entry["id"] for entry in llm_entries if entry.get("id") and "/" in entry["id"]
    }
    assert llm_models, f"{base}{_LLM_MODELS_ENDPOINT} returned no LLM models"

    info_resp = requests.get(f"{base}{_INFO_ENDPOINT}", headers=headers, timeout=30)
    info_resp.raise_for_status()
    info_data = info_resp.json()

    expert_ids: set[str] = set()
    subfeature_paths: set[str] = set()
    for feature in info_data.get("features") or []:
        feature_name = feature.get("name")
        if not feature_name:
            continue
        for subfeature in feature.get("subfeatures") or []:
            subfeature_name = subfeature.get("name")
            if not subfeature_name:
                continue
            subfeature_paths.add(f"{feature_name}/{subfeature_name}")
            for model in subfeature.get("models") or []:
                model_id = model.get("model")
                if model_id:
                    expert_ids.add(model_id)

    assert expert_ids, f"{base}{_INFO_ENDPOINT} returned no expert-model IDs"

    verified_embeddings: set[str] = set()
    for candidate in _EMBEDDING_PROBE_CANDIDATES:
        probe = requests.post(
            f"{base}{_EMBEDDINGS_ENDPOINT}",
            headers=headers,
            json={"model": candidate, "input": "x"},
            timeout=30,
        )
        if probe.status_code == 200:
            verified_embeddings.add(candidate)

    return frozenset(llm_models | expert_ids | subfeature_paths | verified_embeddings)
