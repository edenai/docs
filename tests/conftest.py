"""Pytest configuration for documentation snippet tests."""

import json
import os
import re
import time
from collections.abc import Callable
from pathlib import Path

import pytest
import requests
from dotenv import load_dotenv
from filelock import FileLock
from xdist.plugin import is_xdist_worker

from tests.config_blocks import CATALOG_CACHE_VAR
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
    silent_wav,
)
from tests.helpers.env import env_flag
from tests.snippet_extractor import (
    DEFAULT_BASE_URL,
    MANAGEMENT_KEY_VAR,
    PRODUCTION_TOKEN_VAR,
    SANDBOX_TOKEN_VAR,
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

# For a run that executes no snippet, such as the integration checks: nothing
# else reads the document and image the session uploads for the samples.
_SKIP_UPLOADS_VAR = "EDEN_AI_SKIP_TEST_UPLOADS"

# Credentials a failure report must not print. --showlocals renders every local
# in every frame of the traceback, and a token sits in more of them than the
# ones named after it: a subprocess environment, a client's headers.
_SECRET_VARS = (SANDBOX_TOKEN_VAR, PRODUCTION_TOKEN_VAR, MANAGEMENT_KEY_VAR)

# pytest cuts a long local's repr out of the middle, so what is left of a token
# can be a piece of it. Twelve characters of one are still the token, and are
# more than any other word in a report shares with it by chance.
_SECRET_FRAGMENT_RE = re.compile(r"[A-Za-z0-9_-]{12,}")


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


def pytest_configure(config: pytest.Config) -> None:
    """Publish the suite's credentials under the names third-party SDKs read.

    The integration guides drive Eden AI through frameworks (any-llm, Haystack, aisuite)
    that resolve the key and endpoint from the environment rather than taking
    them as arguments, so their snippets have no placeholder for the extractor
    to rewrite. Runs in the controller and in every xdist worker, because each
    worker executes snippets in its own process.
    """
    sandbox_token = os.environ.get("EDEN_AI_SANDBOX_API_TOKEN")
    if not sandbox_token:
        return
    # Individual tests raise this to the production token where the samples
    # need a real provider answer.
    os.environ["EDENAI_API_KEY"] = sandbox_token
    base_url = os.environ.get("EDEN_AI_BASE_URL", DEFAULT_BASE_URL)
    os.environ["EDENAI_API_BASE"] = f"{base_url}/v3"


@pytest.hookimpl(tryfirst=True)
def pytest_sessionstart(session: pytest.Session) -> None:
    """Clear leftovers, snapshot resources, upload a test file (controller)."""
    # Every process reads the model catalog from one place, worker or not, so
    # every xdist worker collects the same tests from it.
    os.environ[CATALOG_CACHE_VAR] = str(_shared_basetemp(session.config))
    if is_xdist_worker(session):
        return

    state: dict = {}

    if os.environ.get("EDEN_AI_MANAGEMENT_KEY"):
        # A key left active by an earlier run makes the create samples fail
        # with 409 on the duplicate name, so clear those first.
        _clean_up(
            "leftover inference key(s)", lambda: revoke_keys(list_sample_key_ids())
        )

    if os.environ.get("EDEN_AI_SANDBOX_API_TOKEN") and not env_flag(_SKIP_UPLOADS_VAR):
        leftover_files, pre_existing_files = partition_upload_ids()
        _clean_up("leftover uploaded file(s)", lambda: delete_file_ids(leftover_files))
        session.config.stash[pre_existing_files_key] = pre_existing_files
        test_file_id = upload_test_file(minimal_pdf())
        os.environ["_EDEN_TEST_FILE_ID"] = test_file_id
        state["test_file_id"] = test_file_id
        # An image model rejects a PDF outright, so the image feature samples
        # need an upload of their own.
        test_image_id = upload_test_file(minimal_jpeg(), "fixture.jpg")
        os.environ["_EDEN_TEST_IMAGE_ID"] = test_image_id
        state["test_image_id"] = test_image_id

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
        if "test_image_id" in state:
            os.environ.setdefault("_EDEN_TEST_IMAGE_ID", state["test_image_id"])


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

    (d / "recording.wav").write_bytes(silent_wav())

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


def _redact(text: str) -> str:
    """The text with every credential of the run, or a piece of one, hidden."""
    secrets = [os.environ[var] for var in _SECRET_VARS if os.environ.get(var)]
    if not secrets:
        return text
    return _SECRET_FRAGMENT_RE.sub(
        lambda match: (
            "<redacted>"
            if any(match.group(0) in secret for secret in secrets)
            else match.group(0)
        ),
        text,
    )


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Append HTTP details to snippet failures, and hide credentials in all."""
    outcome = yield
    report = outcome.get_result()

    if report.when == "call" and report.failed:
        recorder = item.stash.get(http_interceptor_key, None)
        if recorder is not None:
            summary = recorder.summary()
            if summary != "(no HTTP calls recorded)":
                report.sections.append(("Last HTTP Request/Response", summary))

    if report.failed:
        rendered = str(report.longrepr)
        redacted = _redact(rendered)
        if redacted != rendered:
            report.longrepr = redacted
        report.sections = [
            (title, _redact(content)) for title, content in report.sections
        ]
