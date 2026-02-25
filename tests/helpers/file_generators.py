"""Minimal valid file generators for test fixtures.

Create the smallest valid files of each type for use in documentation
snippet tests. No external dependencies except PIL (for large_jpeg)
and PyPDF2 (for multipage_pdf).
"""

import struct
import zlib


def minimal_pdf() -> bytes:
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


def multipage_pdf(num_pages: int = 6) -> bytes:
    """Valid PDF with multiple blank pages (for PyPDF2 page-extraction tests)."""
    import io

    from PyPDF2 import PdfReader, PdfWriter

    reader = PdfReader(io.BytesIO(minimal_pdf()))
    writer = PdfWriter()
    page = reader.pages[0]
    for _ in range(num_pages):
        writer.add_page(page)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def minimal_jpeg() -> bytes:
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


def large_jpeg(width: int = 4000, height: int = 3000, quality: int = 95) -> bytes:
    """Large valid JPEG file (~several MB) using PIL."""
    import io

    from PIL import Image

    img = Image.new("RGB", (width, height), color=(100, 149, 237))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


def minimal_png() -> bytes:
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
