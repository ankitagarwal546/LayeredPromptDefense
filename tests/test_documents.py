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
    assert result.warnings and "Hidden-text detection is partial" in result.warnings[0]
    assert result.hidden_text == [] and result.removed_invisible_chars == 0


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


def _pdf_with_stream(stream: bytes) -> bytes:
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out, offsets = b"%PDF-1.4\n", []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1) + b"".join(b"%010d 00000 n \n" % o for o in offsets)
    return out + b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)


def test_invisible_characters_are_removed_and_reported():
    result = extract_text("z.txt", "Plain\u200b text\u202e here\x07.".encode())
    assert result.text == "Plain text here." and result.removed_invisible_chars == 3
    assert any("invisible character" in w for w in result.warnings)


def test_hidden_docx_runs_are_reported_but_kept():
    from docx.shared import Pt, RGBColor

    doc = Document()
    p = doc.add_paragraph("Visible start. ")
    white = p.add_run("White instruction.")
    white.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
    p.add_run(" Visible end.")
    tiny = doc.add_paragraph().add_run("Tiny instruction.")
    tiny.font.size = Pt(1)
    vanish = doc.add_paragraph().add_run("Vanished instruction.")
    vanish.font.hidden = True
    doc.add_paragraph("Normal paragraph.")
    buffer = io.BytesIO()
    doc.save(buffer)
    result = extract_text("h.docx", buffer.getvalue())
    assert result.hidden_text == ["White instruction.", "Tiny instruction.", "Vanished instruction."]
    assert "White instruction." in result.text  # kept: the user sees exactly what the model receives
    assert any("look hidden" in w for w in result.warnings)


def test_hidden_pdf_text_is_reported():
    stream = (b"BT /F1 12 Tf 72 720 Td (Visible line.) Tj ET "
              b"BT 1 1 1 rg /F1 12 Tf 72 700 Td (White line.) Tj ET "
              b"BT 0 0 0 rg /F1 1 Tf 72 680 Td (Tiny line.) Tj ET "
              b"BT 0 g 3 Tr /F1 12 Tf 72 660 Td (Invisible mode line.) Tj ET")
    result = extract_text("h.pdf", _pdf_with_stream(stream))
    joined = " ".join(result.hidden_text)
    for piece in ("White line.", "Tiny line.", "Invisible mode line."):
        assert piece in joined and piece in result.text
    assert "Visible line." not in joined


def test_the_hard_injection_test_document_flags_its_white_one_point_text():
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "test_files" / "hard_injection_test.docx"
    if not path.exists():
        pytest.skip("manual test file not present")
    result = extract_text(path.name, path.read_bytes())
    assert any("failed its safety inspection" in h for h in result.hidden_text)
