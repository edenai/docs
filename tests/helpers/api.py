"""Eden AI API helpers for test setup and teardown."""

import os

import requests

# Setup and teardown call the API outside the snippet interceptor that bounds
# snippet requests, so every call here carries its own timeout.
_REQUEST_TIMEOUT = 60

# Cleanup is scoped to the names the documentation samples use, so it can never
# delete or revoke a resource that belongs to someone else in the organization.
FIXTURE_FILE_NAME = "test_fixture.pdf"
SAMPLE_KEY_NAMES = frozenset(
    {"production-v1", "team-backend", "team-daily", "dev-testing"}
)


def api_base_url() -> str:
    return os.environ.get("EDEN_AI_BASE_URL", "https://staging-api.edenai.run")


def api_headers() -> dict:
    token = os.environ.get("EDEN_AI_SANDBOX_API_TOKEN")
    if not token:
        raise RuntimeError("EDEN_AI_SANDBOX_API_TOKEN env var is required")
    return {"Authorization": f"Bearer {token}"}


def _iter_uploads():
    """Yield every uploaded file on the account, walking the pages."""
    page = 1
    while True:
        resp = requests.get(
            f"{api_base_url()}/v3/upload",
            headers=api_headers(),
            params={"page": page, "limit": 1000},
            timeout=_REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        yield from data["items"]
        if page >= data["total_pages"]:
            break
        page += 1


def list_file_ids() -> set[str]:
    """Return the set of all file IDs currently on the account."""
    return {item["file_id"] for item in _iter_uploads()}


def partition_upload_ids() -> tuple[set[str], set[str]]:
    """Split the account's uploads into (fixture leftovers, everything else).

    One walk answers both questions the session start asks: which uploads an
    earlier run left behind, and which ones were already there, so teardown can
    tell what this run uploaded.
    """
    fixture_ids: set[str] = set()
    other_ids: set[str] = set()
    for item in _iter_uploads():
        target = fixture_ids if item["file_name"] == FIXTURE_FILE_NAME else other_ids
        target.add(item["file_id"])
    return fixture_ids, other_ids


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
            timeout=_REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        deleted += resp.json()["deleted_count"]
    return deleted


def upload_test_file(file_bytes: bytes, filename: str = FIXTURE_FILE_NAME) -> str:
    """Upload a file and return its file_id."""
    resp = requests.post(
        f"{api_base_url()}/v3/upload",
        headers=api_headers(),
        files={"file": (filename, file_bytes)},
        timeout=_REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()["file_id"]


def management_headers() -> dict:
    token = os.environ.get("EDEN_AI_MANAGEMENT_KEY")
    if not token:
        raise RuntimeError("EDEN_AI_MANAGEMENT_KEY env var is missing")
    return {"Authorization": f"Bearer {token}"}


def list_sample_key_ids() -> set[str]:
    """Return the ids of the active inference keys the samples create.

    Scoped to SAMPLE_KEY_NAMES, so cleanup can never revoke a key the
    organization actually depends on, whoever created it. Legacy keys that were
    never regenerated have a null id and are skipped: they cannot be addressed
    by URL anyway.
    """
    key_ids: set[str] = set()
    offset = 0
    limit = 100
    while True:
        resp = requests.get(
            f"{api_base_url()}/v3/manage/keys/",
            headers=management_headers(),
            params={"limit": limit, "offset": offset},
            timeout=_REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        for key in data["results"]:
            if key["id"] and not key["revoked"] and key["name"] in SAMPLE_KEY_NAMES:
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
            timeout=_REQUEST_TIMEOUT,
        )
        if resp.status_code == 200:
            revoked += 1
        elif resp.status_code != 404:
            errors.append(f"{key_id}: {resp.status_code} {resp.text}")
    if errors:
        raise RuntimeError("Failed to revoke keys:\n" + "\n".join(errors))
    return revoked
