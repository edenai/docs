"""Pytest configuration for documentation snippet tests.

- Generates minimal test fixture files (PDF, JPEG, etc.) at session start
- Runs the snippet extractor once to produce importable modules
- Provides shared fixtures for test parametrization
"""

import os
import struct
import tempfile
import zlib
from pathlib import Path

import pytest
from dotenv import load_dotenv

from tests.snippet_extractor import extract_all, extract_individual_blocks

# Load tests/.env (if present) — CI uses native env vars instead
load_dotenv(Path(__file__).parent / ".env")


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
    for name in ["document.pdf", "invoice.pdf"]:
        (d / name).write_bytes(pdf_data)

    # JPEG files
    jpeg_data = _minimal_jpeg()
    for name in ["image.jpg", "photo.jpg", "product.jpg", "people.jpg", "passport.jpg"]:
        (d / name).write_bytes(jpeg_data)

    # PNG files
    png_data = _minimal_png()
    (d / "image.png").write_bytes(png_data)

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


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "syntax: syntax-only validation tests")
    config.addinivalue_line("markers", "execute: execution tests requiring API key")
