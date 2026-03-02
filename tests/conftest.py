"""Pytest configuration for documentation snippet tests.

- Generates minimal test fixture files (PDF, JPEG, etc.) at session start
- Uploads a test file to the API and cleans up all new files after tests
- Provides shared fixtures for test parametrization
- Appends HTTP request/response details to failures via pytest hook

Setup and teardown of shared API resources (uploaded files, custom tokens)
run exactly once on the xdist controller process (or the single process when
running without xdist). Workers receive the shared state via env var
inheritance and a JSON file in the shared temp directory.
"""

import json
import os
from pathlib import Path

import pytest
import requests
from dotenv import load_dotenv
from filelock import FileLock
from xdist.plugin import is_xdist_worker

from tests.helpers.api import (
    delete_custom_tokens,
    delete_file_ids,
    list_custom_token_names,
    list_file_ids,
    upload_test_file,
)
from tests.helpers.file_generators import (
    large_jpeg,
    minimal_jpeg,
    minimal_pdf,
    minimal_png,
    multipage_pdf,
)

load_dotenv(Path(__file__).parent / ".env")

http_recorder_key = pytest.StashKey()

_SHARED_STATE_FILE = ".eden_test_shared_state.json"


def _shared_basetemp(config: pytest.Config) -> Path:
    """Return the controller's basetemp directory.

    Under xdist, each worker's basetemp is ``<controller_basetemp>/popen-gwN``,
    so the parent of a worker's basetemp is the controller's basetemp — a
    directory visible to every process.  Without xdist the basetemp itself is
    used (single process).
    """
    basetemp = config._tmp_path_factory.getbasetemp()
    if hasattr(config, "workerinput"):
        return basetemp.parent
    return basetemp


def _shared_state_path(config: pytest.Config) -> Path:
    """Return path to the JSON file shared between controller and workers."""
    return _shared_basetemp(config) / _SHARED_STATE_FILE


# ---------------------------------------------------------------------------
# Controller-only hooks: setup before workers spawn, cleanup after they finish
# ---------------------------------------------------------------------------


@pytest.hookimpl(tryfirst=True)
def pytest_sessionstart(session: pytest.Session) -> None:
    """Snapshot API resources and upload a test file (controller only).

    Runs before xdist's own ``pytest_sessionstart`` (which uses
    ``trylast=True``), so this completes before any worker is spawned.
    Workers inherit ``_EDEN_TEST_FILE_ID`` via the environment and can also
    read the shared JSON file.
    """
    if is_xdist_worker(session):
        return

    state: dict = {}

    if os.environ.get("EDEN_AI_SANDBOX_API_TOKEN"):
        pre_existing_files = list_file_ids()
        test_file_id = upload_test_file(minimal_pdf(), "test_fixture.pdf")
        os.environ["_EDEN_TEST_FILE_ID"] = test_file_id
        state["pre_existing_files"] = sorted(pre_existing_files)
        state["test_file_id"] = test_file_id

    if os.environ.get("EDEN_AI_PRODUCTION_API_TOKEN"):
        state["pre_existing_tokens"] = sorted(list_custom_token_names())

    path = _shared_state_path(session.config)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state))


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Delete API resources created during the test run (controller only).

    Runs after xdist's own ``pytest_sessionfinish`` (which tears down all
    worker nodes first), so every worker has finished before cleanup starts.
    """
    if is_xdist_worker(session):
        return

    path = _shared_state_path(session.config)
    if not path.exists():
        return

    state = json.loads(path.read_text())
    print("\n[conftest] Cleaning up API resources...")

    if "pre_existing_files" in state:
        pre_existing = set(state["pre_existing_files"])
        try:
            current = list_file_ids()
            new_file_ids = current - pre_existing
            if new_file_ids:
                deleted = delete_file_ids(new_file_ids)
                print(f"\n[conftest] Cleaned up {deleted} uploaded file(s)")
        except Exception as exc:
            print(f"\n[conftest] WARNING: file cleanup failed: {exc}")

    if "pre_existing_tokens" in state:
        pre_existing = set(state["pre_existing_tokens"])
        try:
            current = list_custom_token_names()
            new_tokens = current - pre_existing
            if new_tokens:
                deleted = delete_custom_tokens(new_tokens)
                print(f"\n[conftest] Cleaned up {deleted} custom token(s)")
        except Exception as exc:
            print(f"\n[conftest] WARNING: token cleanup failed: {exc}")


# ---------------------------------------------------------------------------
# Worker-side fixture: read shared state written by the controller
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session", autouse=True)
def _load_shared_state(request):
    """Set ``_EDEN_TEST_FILE_ID`` from the controller's shared state file.

    Under normal ``popen`` workers the env var is already inherited, but this
    provides a safety net (e.g. remote xdist workers that don't inherit env).
    """
    path = _shared_state_path(request.config)
    if path.exists():
        state = json.loads(path.read_text())
        if "test_file_id" in state:
            os.environ.setdefault("_EDEN_TEST_FILE_ID", state["test_file_id"])


@pytest.fixture(scope="session")
def fixtures_dir(request):
    """Create a temp directory with minimal test fixture files.

    Under xdist the directory lives in the shared basetemp so every worker
    reuses the same files.  A ``filelock`` ensures only the first process to
    arrive actually writes them.
    """
    d = _shared_basetemp(request.config) / "doc_fixtures"

    with FileLock(str(d) + ".lock"):
        if not d.exists():
            d.mkdir()
            _populate_fixtures_dir(d)

    return d


def _populate_fixtures_dir(d: Path) -> None:
    """Write all fixture files into *d*."""
    pdf_data = minimal_pdf()
    for name in [
        "document.pdf", "invoice.pdf",
        "report.pdf", "contract.pdf", "quarterly-report.pdf",
        "policy-document.pdf", "research-paper.pdf",
        "doc1.pdf", "doc2.pdf", "doc3.pdf",
        "invoice1.pdf", "invoice2.pdf", "invoice3.pdf",
        "doc.pdf",
    ]:
        (d / name).write_bytes(pdf_data)

    (d / "large-report.pdf").write_bytes(multipage_pdf(6))

    jpeg_data = minimal_jpeg()
    for name in [
        "image.jpg", "photo.jpg", "product.jpg", "people.jpg", "passport.jpg", "receipt.jpg",
        "user_upload.jpg", "complex_document.jpg", "user_photo.jpg",
    ]:
        (d / name).write_bytes(jpeg_data)
    (d / "large-image.jpg").write_bytes(large_jpeg())

    png_data = minimal_png()
    for name in ["image.png", "screenshot.png"]:
        (d / name).write_bytes(png_data)

    (d / "app.py").write_text("def main():\n    print('hello')\n")

    (d / "document.txt").write_text(
        "Eden AI is a platform that provides access to multiple AI providers "
        "through a single API. It supports text analysis, image processing, "
        "OCR, and many other AI features."
    )


class HttpRecorder:
    """Records the last HTTP request/response for debugging test failures."""

    def __init__(self):
        self.last_request: requests.PreparedRequest | None = None
        self.last_response: requests.Response | None = None

    def summary(self, max_body: int = 2000) -> str:
        """Format the last recorded request/response for error output."""
        if self.last_request is None:
            return "(no HTTP calls recorded)"

        req = self.last_request
        resp = self.last_response

        lines = [
            f"{req.method} {req.url}",
        ]

        if req.body:
            body = req.body if isinstance(req.body, str) else repr(req.body)
            if len(body) > max_body:
                body = body[:max_body] + f"... ({len(body)} bytes total)"
            lines.append(f"Request body:\n{body}")

        if resp is not None:
            lines.append(f"Status: {resp.status_code}")
            try:
                text = resp.text
                if len(text) > max_body:
                    text = text[:max_body] + f"... ({len(text)} chars total)"
                lines.append(f"Response body:\n{text}")
            except Exception:
                lines.append("Response body: (could not decode)")

        return "\n".join(lines)


@pytest.fixture()
def http_recorder(monkeypatch):
    """Monkeypatch requests.Session.send to record the last request/response."""
    recorder = HttpRecorder()
    original_send = requests.Session.send

    def _recording_send(self, request, **kwargs):
        recorder.last_request = request
        response = original_send(self, request, **kwargs)
        recorder.last_response = response
        return response

    monkeypatch.setattr(requests.Session, "send", _recording_send)
    return recorder


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Append HTTP request/response details to snippet execution failures."""
    outcome = yield
    report = outcome.get_result()

    if report.when == "call" and report.failed:
        recorder = item.stash.get(http_recorder_key, None)
        if recorder is not None:
            summary = recorder.summary()
            if summary != "(no HTTP calls recorded)":
                report.sections.append(
                    ("Last HTTP Request/Response", summary)
                )
