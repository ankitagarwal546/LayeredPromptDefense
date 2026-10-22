import io
import zipfile

import pytest
from docx import Document

from injection_defense.documents import (
    MAX_UPLOAD_BYTES, ExtractionError, extract_text,
)


def make_pdf(text: str) -> bytes:
    """Smallest valid single-page PDF containing `text` (no external libraries needed)."""
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out, offsets = b"%PDF-1.4\n", []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)
    return out


def make_docx(*paragraphs: str, table: list[list[str]] | None = None) -> bytes:
    doc = Document()
    for p in paragraphs:
        doc.add_paragraph(p)
    if table:
        t = doc.add_table(rows=len(table), cols=len(table[0]))
        for r, row in enumerate(table):
            for c, value in enumerate(row):
                t.cell(r, c).text = value
    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()


def test_txt_and_md_are_decoded():
    assert extract_text("a.txt", "héllo".encode()).text == "héllo"
    assert extract_text("NOTES.MD", b"# Title\n\nBody").format == "md"
    assert extract_text("bom.txt", "﻿hi".encode("utf-8")).text == "hi"


def test_pdf_text_is_extracted_with_caveat():
    result = extract_text("p.pdf", make_pdf("Coral reefs are vital"))
    assert "Coral reefs are vital" in result.text and result.format == "pdf"
    assert result.warnings and "Hidden-text injection is not detected" in result.warnings[0]


def test_docx_paragraphs_and_tables_are_extracted():
    result = extract_text("d.docx", make_docx("First paragraph", "Second", table=[["a", "b"], ["c", "d"]]))
    for piece in ("First paragraph", "Second", "a", "d"):
        assert piece in result.text
    assert result.warnings


@pytest.mark.parametrize("name,data,message", [
    ("x.exe", b"MZ...", "Unsupported file type"),
    ("noext", b"hello", "Unsupported file type"),
    ("e.txt", b"", "empty"),
    ("big.txt", b"a" * (MAX_UPLOAD_BYTES + 1), "too large"),
    ("bad.txt", b"\xff\xfe\x00\x01\x80", "UTF-8"),
    ("fake.pdf", b"not a pdf", "not a PDF"),
    ("fake.docx", b"not a zip", "not a DOCX"),
    ("blank.txt", b"   \n  ", "No extractable text"),
])
def test_rejections_are_clear(name, data, message):
    with pytest.raises(ExtractionError, match=message):
        extract_text(name, data)


def test_corrupt_pdf_and_docx_do_not_leak_internals():
    with pytest.raises(ExtractionError) as err:
        extract_text("c.pdf", b"%PDF-1.4\ngarbage garbage")
    assert str(err.value) == "Could not parse the PDF"
    with pytest.raises(ExtractionError) as err:
        extract_text("c.docx", b"PK\x03\x04garbage")
    assert str(err.value) == "Could not parse the DOCX"


def test_text_length_limit_is_enforced_after_extraction():
    with pytest.raises(ExtractionError, match="limit"):
        extract_text("long.txt", b"a" * 50_001)


def test_docx_zip_bomb_is_rejected(monkeypatch):
    monkeypatch.setattr("injection_defense.documents.MAX_DOCX_UNCOMPRESSED_BYTES", 1000)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("word/document.xml", "a" * 100_000)
    with pytest.raises(ExtractionError, match="unreasonable size"):
        extract_text("bomb.docx", buffer.getvalue())


def test_path_components_in_filename_are_ignored():
    assert extract_text("../../etc/passwd.txt", b"hello").text == "hello"
