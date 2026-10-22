"""Text extraction from uploaded files (.txt, .md, .pdf, .docx).

Files are parsed, never executed: no macros, scripts, or embedded objects are run. Extraction
returns plain text exactly as it will be sent to the model, so a researcher can inspect it.

LIMITATION: extraction is not a security control. PDF and DOCX text extraction can include text
a human reader would not see (white-on-white, hidden runs) and can omit content that is only in
images, comments, headers/footers, or metadata. This project does NOT detect hidden-text attacks.
"""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass, field
from pathlib import PurePath

from injection_defense.config import MAX_DOCUMENT_CHARS

MAX_UPLOAD_BYTES = 5_000_000
MAX_PDF_PAGES = 200
MAX_DOCX_UNCOMPRESSED_BYTES = 50_000_000  # guards against zip bombs
SUPPORTED_EXTENSIONS = (".txt", ".md", ".pdf", ".docx")

EXTRACTION_CAVEAT = (
    "Extracted text may include content invisible to a human reader and may omit images, comments, "
    "headers/footers and metadata. Hidden-text injection is not detected by this application."
)


class ExtractionError(ValueError):
    """The upload was rejected; the message is safe to show to the user."""


@dataclass(frozen=True)
class ExtractionResult:
    text: str
    format: str
    warnings: list[str] = field(default_factory=list)

    @property
    def chars(self) -> int:
        return len(self.text)


def extract_text(filename: str, data: bytes) -> ExtractionResult:
    extension = PurePath(filename or "").suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise ExtractionError(f"Unsupported file type {extension or '(none)'!r}; use {', '.join(SUPPORTED_EXTENSIONS)}")
    if not data:
        raise ExtractionError("The file is empty")
    if len(data) > MAX_UPLOAD_BYTES:
        raise ExtractionError(f"File too large (limit {MAX_UPLOAD_BYTES:,} bytes)")

    if extension in (".txt", ".md"):
        result = ExtractionResult(_decode_text(data), extension[1:])
    elif extension == ".pdf":
        result = _extract_pdf(data)
    else:
        result = _extract_docx(data)

    if not result.text.strip():
        raise ExtractionError("No extractable text found (scanned images are not OCR'd)")
    if result.chars > MAX_DOCUMENT_CHARS:
        raise ExtractionError(f"Extracted text is {result.chars:,} characters; the limit is {MAX_DOCUMENT_CHARS:,}")
    return result


def _decode_text(data: bytes) -> str:
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ExtractionError("Text files must be UTF-8 encoded") from None


def _extract_pdf(data: bytes) -> ExtractionResult:
    if not data.startswith(b"%PDF-"):
        raise ExtractionError("File content is not a PDF")
    from pypdf import PdfReader

    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise ExtractionError("Encrypted PDFs are not supported")
        pages = reader.pages
        if len(pages) > MAX_PDF_PAGES:
            raise ExtractionError(f"PDF has {len(pages)} pages; the limit is {MAX_PDF_PAGES}")
        text = "\n\n".join((page.extract_text() or "").strip() for page in pages)
    except ExtractionError:
        raise
    except Exception:  # pypdf raises many types on malformed input; never leak details
        raise ExtractionError("Could not parse the PDF") from None
    return ExtractionResult(text, "pdf", [EXTRACTION_CAVEAT])


def _extract_docx(data: bytes) -> ExtractionResult:
    if not data.startswith(b"PK\x03\x04"):
        raise ExtractionError("File content is not a DOCX")
    from docx import Document

    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            if sum(info.file_size for info in archive.infolist()) > MAX_DOCX_UNCOMPRESSED_BYTES:
                raise ExtractionError("DOCX expands to an unreasonable size")
        document = Document(io.BytesIO(data))
        parts = [p.text for p in document.paragraphs]
        for table in document.tables:
            parts += [cell.text for row in table.rows for cell in row.cells]
    except ExtractionError:
        raise
    except Exception:
        raise ExtractionError("Could not parse the DOCX") from None
    return ExtractionResult("\n".join(parts), "docx", [EXTRACTION_CAVEAT])
