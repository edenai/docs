"""Pytest configuration for documentation snippet tests.

- Generates minimal test fixture files (PDF, JPEG, etc.) at session start
- Runs the snippet extractor once to produce importable modules
- Provides shared fixtures for test parametrization
- Uploads a test file to the API and cleans up all new files after tests
"""

import os
import struct
import tempfile
import zlib
from pathlib import Path

import pytest
import requests
from dotenv import load_dotenv

from tests.snippet_extractor import extract_all, extract_individual_blocks

# Load tests/.env (if present) — CI uses native env vars instead
load_dotenv(Path(__file__).parent / ".env")

# The placeholder UUID used in documentation snippets
_PLACEHOLDER_FILE_ID = "550e8400-e29b-41d4-a716-446655440000"


# ---------------------------------------------------------------------------
# Eden AI file management helpers
# ---------------------------------------------------------------------------

def _api_base_url() -> str:
    return os.environ.get("EDEN_AI_BASE_URL", "https://api.edenai.run")


def _api_headers() -> dict:
    return {"Authorization": f"Bearer {os.environ['EDEN_AI_SANDBOX_API_TOKEN']}"}


def _list_file_ids() -> set[str]:
    """Return the set of all file IDs currently on the account."""
    file_ids: set[str] = set()
    page = 1
    while True:
        resp = requests.get(
            f"{_api_base_url()}/v3/upload",
            headers=_api_headers(),
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


def _delete_file_ids(file_ids: set[str]) -> int:
    """Delete files by ID (batches of 100). Returns total deleted count."""
    if not file_ids:
        return 0
    deleted = 0
    batch = []
    for fid in file_ids:
        batch.append(fid)
        if len(batch) == 100:
            resp = requests.post(
                f"{_api_base_url()}/v3/upload/delete",
                headers={**_api_headers(), "Content-Type": "application/json"},
                json={"file_ids": batch},
            )
            resp.raise_for_status()
            deleted += resp.json()["deleted_count"]
            batch = []
    if batch:
        resp = requests.post(
            f"{_api_base_url()}/v3/upload/delete",
            headers={**_api_headers(), "Content-Type": "application/json"},
            json={"file_ids": batch},
        )
        resp.raise_for_status()
        deleted += resp.json()["deleted_count"]
    return deleted


def _upload_test_file(file_bytes: bytes, filename: str) -> str:
    """Upload a file and return its file_id."""
    resp = requests.post(
        f"{_api_base_url()}/v3/upload",
        headers=_api_headers(),
        files={"file": (filename, file_bytes)},
    )
    resp.raise_for_status()
    return resp.json()["file_id"]


# ---------------------------------------------------------------------------
# Custom token management helpers (v2 admin endpoints)
# ---------------------------------------------------------------------------

def _production_api_headers() -> dict:
    token = os.environ.get("EDEN_AI_PRODUCTION_API_TOKEN")
    if not token:
        return {}
    return {"Authorization": f"Bearer {token}"}


def _list_custom_token_names() -> set[str]:
    """Return the set of all custom token names currently on the account."""
    headers = _production_api_headers()
    if not headers:
        return set()
    resp = requests.get(
        f"{_api_base_url()}/v2/user/custom_token/",
        headers=headers,
    )
    resp.raise_for_status()
    return {t["name"] for t in resp.json()}


def _delete_custom_tokens(names: set[str]) -> int:
    """Delete custom tokens by name. Returns count of deleted tokens."""
    if not names:
        return 0
    headers = _production_api_headers()
    if not headers:
        return 0
    deleted = 0
    for name in names:
        resp = requests.delete(
            f"{_api_base_url()}/v2/user/custom_token/{name}/",
            headers=headers,
        )
        if resp.status_code == 204:
            deleted += 1
    return deleted


# ---------------------------------------------------------------------------
# Minimal valid file generators (no external dependencies)
# ---------------------------------------------------------------------------

def _minimal_pdf() -> bytes:
    """Smallest valid PDF file (~200 bytes)."""
    return (
        b"%PDF-1.0\n"
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        b"3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R>>endobj\n"
        b"xref\n0 4\n"
        b"0000000000 65535 f \n"
        b"0000000009 00000 n \n"
        b"0000000058 00000 n \n"
        b"0000000115 00000 n \n"
        b"trailer<</Size 4/Root 1 0 R>>\n"
        b"startxref\n190\n%%EOF"
    )


def _multipage_pdf(num_pages: int = 6) -> bytes:
    """Valid PDF with multiple blank pages (for PyPDF2 page-extraction tests)."""
    import io
    from PyPDF2 import PdfReader, PdfWriter

    reader = PdfReader(io.BytesIO(_minimal_pdf()))
    writer = PdfWriter()
    page = reader.pages[0]
    for _ in range(num_pages):
        writer.add_page(page)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _minimal_jpeg() -> bytes:
    """Smallest valid JPEG file (1x1 white pixel)."""
    return bytes([
        0xFF, 0xD8, 0xFF, 0xE0,  # SOI + APP0 marker
        0x00, 0x10,               # APP0 length
        0x4A, 0x46, 0x49, 0x46, 0x00,  # "JFIF\0"
        0x01, 0x01,               # Version
        0x00,                     # Aspect ratio units
        0x00, 0x01, 0x00, 0x01,  # X/Y density
        0x00, 0x00,               # No thumbnail
        0xFF, 0xDB,               # DQT marker
        0x00, 0x43, 0x00,        # DQT length + precision/table ID
    ] + [0x01] * 64 + [          # Quantization table (all 1s)
        0xFF, 0xC0,               # SOF0 marker
        0x00, 0x0B,               # SOF0 length
        0x08,                     # Precision
        0x00, 0x01, 0x00, 0x01,  # Height=1, Width=1
        0x01,                     # Number of components
        0x01, 0x11, 0x00,        # Component 1: ID=1, sampling=1x1, quant table 0
        0xFF, 0xC4,               # DHT marker
        0x00, 0x1F, 0x00,        # DHT length + class/table ID (DC, table 0)
    ] + [0x00] * 16 + [          # Number of codes per length (all 0 = 1 code of length 1)
        0x00,                     # Symbol
        0xFF, 0xC4,               # DHT marker (AC table)
        0x00, 0x1F, 0x10,        # DHT length + class/table ID (AC, table 0)
    ] + [0x00] * 16 + [          # Number of codes per length
        0x00,                     # Symbol
        0xFF, 0xDA,               # SOS marker
        0x00, 0x08,               # SOS length
        0x01,                     # Number of components
        0x01, 0x00,               # Component 1, DC/AC table 0/0
        0x00, 0x3F, 0x00,        # Spectral selection + approximation
        0x7F, 0x50,               # Compressed data (single white pixel)
        0xFF, 0xD9,               # EOI
    ])


def _large_jpeg(width: int = 4000, height: int = 3000, quality: int = 95) -> bytes:
    """Large valid JPEG file (~several MB) using PIL."""
    import io
    from PIL import Image

    img = Image.new("RGB", (width, height), color=(100, 149, 237))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


def _minimal_png() -> bytes:
    """Smallest valid PNG file (1x1 white pixel)."""
    def _chunk(chunk_type: bytes, data: bytes) -> bytes:
        chunk_data = chunk_type + data
        crc = struct.pack(">I", zlib.crc32(chunk_data) & 0xFFFFFFFF)
        return struct.pack(">I", len(data)) + chunk_data + crc

    signature = b"\x89PNG\r\n\x1a\n"
    ihdr = _chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
    raw_data = b"\x00\xff\xff\xff"  # filter byte + RGB white pixel
    idat = _chunk(b"IDAT", zlib.compress(raw_data))
    iend = _chunk(b"IEND", b"")
    return signature + ihdr + idat + iend


# ---------------------------------------------------------------------------
# Session-scoped fixtures
# ---------------------------------------------------------------------------

_extracted_modules = None
_extracted_blocks = None


def _get_extracted_modules():
    global _extracted_modules
    if _extracted_modules is None:
        _extracted_modules = extract_all()
    return _extracted_modules


def _get_extracted_blocks():
    global _extracted_blocks
    if _extracted_blocks is None:
        _extracted_blocks = extract_individual_blocks()
    return _extracted_blocks


@pytest.fixture(scope="session")
def fixtures_dir(tmp_path_factory):
    """Create a temp directory with minimal test fixture files."""
    d = tmp_path_factory.mktemp("doc_fixtures")

    # PDF files
    pdf_data = _minimal_pdf()
    for name in [
        "document.pdf", "invoice.pdf",
        "report.pdf", "contract.pdf", "quarterly-report.pdf",
        "policy-document.pdf", "research-paper.pdf",
        "doc1.pdf", "doc2.pdf", "doc3.pdf",
        "invoice1.pdf", "invoice2.pdf", "invoice3.pdf",
        "doc.pdf",
    ]:
        (d / name).write_bytes(pdf_data)

    # Multi-page PDF (for PyPDF2 page-extraction snippets)
    (d / "large-report.pdf").write_bytes(_multipage_pdf(6))

    # JPEG files
    jpeg_data = _minimal_jpeg()
    for name in [
        "image.jpg", "photo.jpg", "product.jpg", "people.jpg", "passport.jpg", "receipt.jpg",
        "user_upload.jpg", "complex_document.jpg", "user_photo.jpg",
    ]:
        (d / name).write_bytes(jpeg_data)
    (d / "large-image.jpg").write_bytes(_large_jpeg())

    # PNG files
    png_data = _minimal_png()
    for name in ["image.png", "screenshot.png"]:
        (d / name).write_bytes(png_data)

    # Python file (for code review examples)
    (d / "app.py").write_text("def main():\n    print('hello')\n")

    # Text file (for LangChain RAG examples)
    (d / "document.txt").write_text(
        "Eden AI is a platform that provides access to multiple AI providers "
        "through a single API. It supports text analysis, image processing, "
        "OCR, and many other AI features."
    )

    return d


@pytest.fixture(scope="session")
def extracted_modules():
    """Run the snippet extractor and return module metadata."""
    return _get_extracted_modules()


@pytest.fixture(scope="session")
def extracted_blocks():
    """Return individual code blocks for syntax testing."""
    return _get_extracted_blocks()


@pytest.fixture(scope="session", autouse=True)
def manage_uploaded_files():
    """Upload a test file, track files, and clean up after all tests.

    - Snapshots existing file IDs before tests start
    - Uploads a minimal PDF so snippets referencing the placeholder UUID work
    - Sets _EDEN_TEST_FILE_ID env var for generated modules to use
    - After all tests, deletes every file that wasn't present before
    """
    if not os.environ.get("EDEN_AI_SANDBOX_API_TOKEN"):
        yield  # no API key — nothing to manage
        return

    # Snapshot file IDs that already exist (we won't delete these)
    pre_existing = _list_file_ids()

    # Upload a minimal test PDF and expose its ID
    test_file_id = _upload_test_file(_minimal_pdf(), "test_fixture.pdf")
    os.environ["_EDEN_TEST_FILE_ID"] = test_file_id

    yield

    # Cleanup: delete every file created during the test session
    current = _list_file_ids()
    new_file_ids = current - pre_existing
    if new_file_ids:
        deleted = _delete_file_ids(new_file_ids)
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

    pre_existing = _list_custom_token_names()

    yield

    current = _list_custom_token_names()
    new_tokens = current - pre_existing
    if new_tokens:
        deleted = _delete_custom_tokens(new_tokens)
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

        # Request body
        if req.body:
            body = req.body if isinstance(req.body, str) else repr(req.body)
            if len(body) > max_body:
                body = body[:max_body] + f"... ({len(body)} bytes total)"
            lines.append(f"Request body:\n{body}")

        # Response
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


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "syntax: syntax-only validation tests")
    config.addinivalue_line("markers", "execute: execution tests requiring API key")
