"""Pytest configuration for documentation snippet tests.

- Generates minimal test fixture files (PDF, JPEG, etc.) at session start
- Uploads a test file to the API and cleans up all new files after tests
- Provides shared fixtures for test parametrization
- Appends HTTP request/response details to failures via pytest hook
"""

import os
from pathlib import Path

import pytest
import requests
from dotenv import load_dotenv

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


@pytest.fixture(scope="session")
def fixtures_dir(tmp_path_factory):
    """Create a temp directory with minimal test fixture files."""
    d = tmp_path_factory.mktemp("doc_fixtures")

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

    return d


@pytest.fixture(scope="session", autouse=True)
def manage_uploaded_files():
    """Upload a test file, track files, and clean up after all tests.

    - Snapshots existing file IDs before tests start
    - Uploads a minimal PDF so snippets referencing the placeholder UUID work
    - Sets _EDEN_TEST_FILE_ID env var for generated modules to use
    - After all tests, deletes every file that wasn't present before
    """
    if not os.environ.get("EDEN_AI_SANDBOX_API_TOKEN"):
        yield
        return

    pre_existing = list_file_ids()
    test_file_id = upload_test_file(minimal_pdf(), "test_fixture.pdf")
    os.environ["_EDEN_TEST_FILE_ID"] = test_file_id

    yield

    current = list_file_ids()
    new_file_ids = current - pre_existing
    if new_file_ids:
        deleted = delete_file_ids(new_file_ids)
        print(f"\n[conftest] Cleaned up {deleted} uploaded file(s)")


@pytest.fixture(scope="session", autouse=True)
def manage_custom_tokens():
    """Snapshot custom token names before tests, clean up new ones after.

    Ensures tokens created by documentation snippets (e.g. manage-tokens.mdx)
    don't accumulate across test runs.
    """
    if not os.environ.get("EDEN_AI_PRODUCTION_API_TOKEN"):
        yield
        return

    pre_existing = list_custom_token_names()

    yield

    current = list_custom_token_names()
    new_tokens = current - pre_existing
    if new_tokens:
        deleted = delete_custom_tokens(new_tokens)
        print(f"\n[conftest] Cleaned up {deleted} custom token(s)")


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
