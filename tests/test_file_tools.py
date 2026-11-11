"""Tests for File Tools & Converters: Image-to-PDF, PDF-to-Image, Compression, Merging."""

import io
import pytest
from fastapi.testclient import TestClient
from PIL import Image
import pypdf
from backend.main import app


@pytest.fixture
def client():
    return TestClient(app)


def _make_dummy_image_bytes(color=(255, 0, 0), size=(100, 100)) -> bytes:
    img = Image.new("RGB", size, color=color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _make_dummy_pdf_bytes(text="Hello RuleWise") -> bytes:
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def test_convert_image_to_pdf(client):
    """POST /api/v1/files/convert/image-to-pdf converts images to PDF."""
    img1 = _make_dummy_image_bytes(color=(255, 0, 0))
    img2 = _make_dummy_image_bytes(color=(0, 255, 0))

    files = [
        ("files", ("image1.png", img1, "image/png")),
        ("files", ("image2.png", img2, "image/png")),
    ]
    resp = client.post("/api/v1/files/convert/image-to-pdf", files=files)
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert len(resp.content) > 100


def test_convert_pdf_to_images(client):
    """POST /api/v1/files/convert/pdf-to-images extracts images as ZIP."""
    pdf = _make_dummy_pdf_bytes()
    files = {"file": ("document.pdf", pdf, "application/pdf")}
    resp = client.post("/api/v1/files/convert/pdf-to-images", files=files)
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"


def test_compress_file(client):
    """POST /api/v1/files/compress compresses image or PDF."""
    img = _make_dummy_image_bytes(size=(300, 300))
    files = {"file": ("photo.png", img, "image/png")}
    data = {"quality": 50}
    resp = client.post("/api/v1/files/compress", files=files, data=data)
    assert resp.status_code == 200
    assert len(resp.content) > 50


def test_merge_pdfs(client):
    """POST /api/v1/files/merge-pdfs merges multiple PDFs into a single file."""
    pdf1 = _make_dummy_pdf_bytes("Page 1")
    pdf2 = _make_dummy_pdf_bytes("Page 2")

    files = [
        ("files", ("doc1.pdf", pdf1, "application/pdf")),
        ("files", ("doc2.pdf", pdf2, "application/pdf")),
    ]
    resp = client.post("/api/v1/files/merge-pdfs", files=files)
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"

    reader = pypdf.PdfReader(io.BytesIO(resp.content))
    assert len(reader.pages) == 2

