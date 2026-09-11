"""Pytest configuration for documentation snippet tests."""

import json
import os
import time
from collections.abc import Callable
from pathlib import Path

import pytest
import requests
from dotenv import load_dotenv
from filelock import FileLock
from xdist.plugin import is_xdist_worker

from tests.helpers.api import (
    delete_file_ids,
    list_file_ids,
    list_sample_key_ids,
    partition_upload_ids,
    revoke_keys,
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

http_interceptor_key = pytest.StashKey()
# Uploads already on the account when the session started. Both hooks that use
# it run in the controller, so it never needs to reach a worker.
pre_existing_files_key = pytest.StashKey[set]()

_SHARED_STATE_FILE = ".eden_test_shared_state.json"

# Applied to every snippet HTTP call that does not set its own timeout.
_DEFAULT_HTTP_TIMEOUT = 120
# Upper bound on how long a 429 retry waits, whatever Retry-After says.
_MAX_RETRY_AFTER = 30


def _shared_basetemp(config: pytest.Config) -> Path:
    """Return the controller's basetemp directory."""
    basetemp = config._tmp_path_factory.getbasetemp()
    if hasattr(config, "workerinput"):
        return basetemp.parent
    return basetemp


def _shared_state_path(config: pytest.Config) -> Path:
    """Return path to the JSON file shared between controller and workers."""
    return _shared_basetemp(config) / _SHARED_STATE_FILE


def _clean_up(description: str, action: Callable[[], int]) -> bool:
    """Remove test resources, reporting failure instead of raising.

    Returns whether the sweep succeeded, so a caller that cannot tolerate
    leftovers can escalate. Cleanup runs either side of the session: a
    cancelled or crashed run never reaches its teardown, so the next one clears
    what it left behind before starting.
    """
    try:
        removed = action()
    except Exception as exc:
        print(f"\n[conftest] WARNING: {description} cleanup failed: {exc}")
        return False
    if removed:
        print(f"\n[conftest] Cleaned up {removed} {description}")
    return True


@pytest.hookimpl(tryfirst=True)
def pytest_sessionstart(session: pytest.Session) -> None:
    """Clear leftovers, snapshot resources, upload a test file (controller)."""
    if is_xdist_worker(session):
        return

    state: dict = {}

    if os.environ.get("EDEN_AI_MANAGEMENT_KEY"):
        # A key left active by an earlier run makes the create samples fail
        # with 409 on the duplicate name, so clear those first.
        _clean_up(
            "leftover inference key(s)", lambda: revoke_keys(list_sample_key_ids())
        )

    if os.environ.get("EDEN_AI_SANDBOX_API_TOKEN"):
        leftover_files, pre_existing_files = partition_upload_ids()
        _clean_up("leftover uploaded file(s)", lambda: delete_file_ids(leftover_files))
        session.config.stash[pre_existing_files_key] = pre_existing_files
        test_file_id = upload_test_file(minimal_pdf())
        os.environ["_EDEN_TEST_FILE_ID"] = test_file_id
        state["test_file_id"] = test_file_id

    path = _shared_state_path(session.config)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state))


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Delete API resources created during the test run (controller only)."""
    if is_xdist_worker(session):
        return

    pre_existing = session.config.stash.get(pre_existing_files_key, None)
    if pre_existing is not None:
        _clean_up(
            "uploaded file(s)", lambda: delete_file_ids(list_file_ids() - pre_existing)
        )

    if os.environ.get("EDEN_AI_MANAGEMENT_KEY"):
        # An inference key that outlives the run can still spend the
        # organization's credit, so failing to revoke one fails the session
        # instead of passing with a warning nobody reads.
        revoked = _clean_up(
            "inference key(s)", lambda: revoke_keys(list_sample_key_ids())
        )
        if not revoked:
            session.exitstatus = pytest.ExitCode.TESTS_FAILED


@pytest.fixture(scope="session", autouse=True)
def _load_shared_state(request):
    """Load shared state (e.g. test file ID) from the controller's JSON file."""
    path = _shared_state_path(request.config)
    if path.exists():
        state = json.loads(path.read_text())
        if "test_file_id" in state:
            os.environ.setdefault("_EDEN_TEST_FILE_ID", state["test_file_id"])


@pytest.fixture(scope="session")
def fixtures_dir(request):
    """Create a temp directory with minimal test fixture files."""
    d = _shared_basetemp(request.config) / "doc_fixtures"

    with FileLock(str(d) + ".lock"):
        if not d.exists():
            d.mkdir()
            _populate_fixtures_dir(d)

    return d


def _populate_fixtures_dir(d: Path) -> None:
    pdf_data = minimal_pdf()
    for name in [
        "document.pdf",
        "invoice.pdf",
        "report.pdf",
        "contract.pdf",
        "quarterly-report.pdf",
        "policy-document.pdf",
        "research-paper.pdf",
        "doc1.pdf",
        "doc2.pdf",
        "doc3.pdf",
        "invoice1.pdf",
        "invoice2.pdf",
        "invoice3.pdf",
        "doc.pdf",
    ]:
        (d / name).write_bytes(pdf_data)

    (d / "large-report.pdf").write_bytes(multipage_pdf(6))

    jpeg_data = minimal_jpeg()
    for name in [
        "image.jpg",
        "photo.jpg",
        "product.jpg",
        "people.jpg",
        "passport.jpg",
        "receipt.jpg",
        "user_upload.jpg",
        "complex_document.jpg",
        "user_photo.jpg",
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
    """Stores the last HTTP request/response for debugging test failures."""

    def __init__(self):
        self.last_request: requests.PreparedRequest | None = None
        self.last_response: requests.Response | None = None

    def summary(self, max_body: int = 2000) -> str:
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
def http_interceptor(monkeypatch, request):
    """Monkeypatch requests.Session.send to record requests and retry on 429."""
    recorder = HttpRecorder()
    request.node.stash[http_interceptor_key] = recorder
    original_send = requests.Session.send

    def _intercepted_send(self, prepared_request, **kwargs):
        # Snippets never pass a timeout, so a request the API never answers
        # would hold a worker until the job is killed. Turn that into a
        # ReadTimeout with the request details attached to the failure.
        if kwargs.get("timeout") is None:
            kwargs["timeout"] = _DEFAULT_HTTP_TIMEOUT
        recorder.last_request = prepared_request
        response = original_send(self, prepared_request, **kwargs)
        recorder.last_response = response
        retries = 0
        while response.status_code == 429 and retries < 5:
            retry_after = float(response.headers.get("Retry-After", 1))
            time.sleep(min(retry_after, _MAX_RETRY_AFTER))
            response = original_send(self, prepared_request, **kwargs)
            recorder.last_response = response
            retries += 1
        return response

    monkeypatch.setattr(requests.Session, "send", _intercepted_send)
    return recorder


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Append HTTP request/response details to snippet execution failures."""
    outcome = yield
    report = outcome.get_result()

    if report.when == "call" and report.failed:
        recorder = item.stash.get(http_interceptor_key, None)
        if recorder is not None:
            summary = recorder.summary()
            if summary != "(no HTTP calls recorded)":
                report.sections.append(("Last HTTP Request/Response", summary))
