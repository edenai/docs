"""Eden AI API helpers for test setup and teardown."""

import os

import requests


def api_base_url() -> str:
    return os.environ.get("EDEN_AI_BASE_URL", "https://staging-api.edenai.run")


def api_headers() -> dict:
    token = os.environ.get("EDEN_AI_SANDBOX_API_TOKEN")
    if not token:
        raise RuntimeError("EDEN_AI_SANDBOX_API_TOKEN env var is required")
    return {"Authorization": f"Bearer {token}"}


def list_file_ids() -> set[str]:
    """Return the set of all file IDs currently on the account."""
    file_ids: set[str] = set()
    page = 1
    while True:
        resp = requests.get(
            f"{api_base_url()}/v3/upload",
            headers=api_headers(),
            params={"page": page, "limit": 1000},
        )
        resp.raise_for_status()
        data = resp.json()
        for item in data["items"]:
            file_ids.add(item["file_id"])
        if page >= data["total_pages"]:
            break
        page += 1
    return file_ids


def delete_file_ids(file_ids: set[str]) -> int:
    """Delete files by ID (batches of 100). Returns total deleted count."""
    if not file_ids:
        return 0
    deleted = 0
    ids_list = list(file_ids)
    for start in range(0, len(ids_list), 100):
        batch = ids_list[start : start + 100]
        resp = requests.post(
            f"{api_base_url()}/v3/upload/delete",
            headers={**api_headers(), "Content-Type": "application/json"},
            json={"file_ids": batch},
        )
        resp.raise_for_status()
        deleted += resp.json()["deleted_count"]
    return deleted


def upload_test_file(file_bytes: bytes, filename: str) -> str:
    """Upload a file and return its file_id."""
    resp = requests.post(
        f"{api_base_url()}/v3/upload",
        headers=api_headers(),
        files={"file": (filename, file_bytes)},
    )
    resp.raise_for_status()
    return resp.json()["file_id"]


def production_api_headers() -> dict:
    token = os.environ.get("EDEN_AI_PRODUCTION_API_TOKEN")
    if not token:
        raise RuntimeError("EDEN_AI_PRODUCTION_API_TOKEN env var is missing")
    return {"Authorization": f"Bearer {token}"}


def list_custom_token_names() -> set[str]:
    """Return the set of all custom token names currently on the account."""
    resp = requests.get(
        f"{api_base_url()}/v2/user/custom_token/",
        headers=production_api_headers(),
    )
    resp.raise_for_status()
    return {t["name"] for t in resp.json()}


def create_custom_token(name: str, **kwargs) -> dict:
    """Create a custom token and return the response JSON."""
    payload = {"name": name, **kwargs}
    resp = requests.post(
        f"{api_base_url()}/v2/user/custom_token/",
        headers=production_api_headers(),
        json=payload,
    )
    resp.raise_for_status()
    return resp.json()


def delete_custom_tokens(names: set[str]) -> int:
    """Delete custom tokens by name. Returns count of deleted tokens."""
    if not names:
        return 0
    deleted = 0
    errors = []
    for name in names:
        resp = requests.delete(
            f"{api_base_url()}/v2/user/custom_token/{name}/",
            headers=production_api_headers(),
        )
        if resp.status_code == 204:
            deleted += 1
        elif resp.status_code != 404:
            errors.append(f"{name}: {resp.status_code} {resp.text}")
    if errors:
        raise RuntimeError("Failed to delete custom tokens:\n" + "\n".join(errors))
    return deleted
