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


def management_headers() -> dict:
    token = os.environ.get("EDEN_AI_MANAGEMENT_KEY")
    if not token:
        raise RuntimeError("EDEN_AI_MANAGEMENT_KEY env var is missing")
    return {"Authorization": f"Bearer {token}"}


def list_active_key_ids() -> set[str]:
    """Return the ids of every non-revoked inference key in the organization.

    Legacy keys that were never regenerated have a null id and are skipped:
    they cannot be addressed by URL anyway.
    """
    key_ids: set[str] = set()
    offset = 0
    limit = 100
    while True:
        resp = requests.get(
            f"{api_base_url()}/v3/manage/keys/",
            headers=management_headers(),
            params={"limit": limit, "offset": offset},
        )
        resp.raise_for_status()
        data = resp.json()
        for key in data["results"]:
            if key["id"] and not key["revoked"]:
                key_ids.add(key["id"])
        offset += limit
        if offset >= data["total_count"]:
            break
    return key_ids


def revoke_keys(key_ids: set[str]) -> int:
    """Revoke inference keys by id. Returns the number of keys revoked.

    Revocation is permanent: the keys stay listed with ``revoked: true``.
    """
    if not key_ids:
        return 0
    revoked = 0
    errors = []
    for key_id in key_ids:
        resp = requests.delete(
            f"{api_base_url()}/v3/manage/keys/{key_id}/",
            headers=management_headers(),
        )
        if resp.status_code == 200:
            revoked += 1
        elif resp.status_code != 404:
            errors.append(f"{key_id}: {resp.status_code} {resp.text}")
    if errors:
        raise RuntimeError("Failed to revoke keys:\n" + "\n".join(errors))
    return revoked
