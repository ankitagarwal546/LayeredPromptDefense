"""Text extraction from uploaded files (.txt, .md, .pdf, .docx).

Files are parsed, never executed: no macros, scripts, or embedded objects are run. Extraction
returns plain text exactly as it will be sent to the model, so a researcher can inspect it.

LIMITATION: extraction is not a security control. PDF and DOCX text extraction can include text
a human reader would not see (white-on-white, hidden runs) and can omit content that is only in
images, comments, headers/footers, or metadata. Hidden-text detection here is partial and heuristic:
invisible characters (zero-width, bidirectional overrides, control characters) are removed and
reported; DOCX runs that are hidden, tiny (<= 2 pt) or near-white, and PDF text drawn tiny, near-white
or in invisible render mode are reported (and kept in the text, so the user sees what the model sees).
Text hidden by other means (behind images, off-page, same colour as a coloured background, style-level
formatting) is not detected.
"""

from __future__ import annotations

import io
import math
import re
import unicodedata
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
    "headers/footers and metadata. Hidden-text detection is partial: tiny, near-white or hidden text and "
    "invisible characters are reported; other hiding tricks are not detected."
)
HIDDEN_MAX_POINTS = 2.0  # text at or below this size is treated as hidden
_NEAR_WHITE = 0.94  # every colour channel at or above this (0-1) counts as near-white
MAX_HIDDEN_SNIPPETS = 20
# Zero-width characters, bidirectional embedding/override/isolate controls, and other format characters that
# can hide or visually reorder text. Ordinary whitespace (\n, \t, \r) is kept.
_INVISIBLE = re.compile("[\u200b-\u200f\u202a-\u202e\u2060-\u2064\u2066-\u2069\ufeff\u00ad]")


class ExtractionError(ValueError):
    """The upload was rejected; the message is safe to show to the user."""


@dataclass(frozen=True)
class ExtractionResult:
    text: str
    format: str
    warnings: list[str] = field(default_factory=list)
    hidden_text: list[str] = field(default_factory=list)  # snippets that look invisible to a reader (kept in `text`)
    removed_invisible_chars: int = 0

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
    result = _report_hidden(result)

    if not result.text.strip():
        raise ExtractionError("No extractable text found (scanned images are not OCR'd)")
    if result.chars > MAX_DOCUMENT_CHARS:
        raise ExtractionError(f"Extracted text is {result.chars:,} characters; the limit is {MAX_DOCUMENT_CHARS:,}")
    return result


def strip_invisible(text: str) -> tuple[str, int]:
    """Remove invisible format characters and control characters (except newline, tab, CR); return (text, count)."""
    cleaned = _INVISIBLE.sub("", text)
    cleaned = "".join(ch for ch in cleaned if ch in "\n\t\r" or unicodedata.category(ch) != "Cc")
    return cleaned, len(text) - len(cleaned)


def _report_hidden(result: ExtractionResult) -> ExtractionResult:
    text, removed = strip_invisible(result.text)
    warnings = list(result.warnings)
    if removed:
        warnings.append(f"Removed {removed} invisible character(s) (zero-width, bidirectional-override or control "
                        "characters), which can hide or visually reorder text.")
    hidden = [s for s in dict.fromkeys(_short(strip_invisible(h)[0]) for h in result.hidden_text) if s][:MAX_HIDDEN_SNIPPETS]
    if hidden:
        warnings.append(f"{len(hidden)} passage(s) look hidden from a human reader (tiny, near-white or hidden text) "
                        "but are included in the text the model receives. Check them: hidden text is a common way to plant instructions.")
    return ExtractionResult(text, result.format, warnings, hidden, removed)


def _short(s: str, limit: int = 200) -> str:
    s = " ".join(s.split())
    return s if len(s) <= limit else s[: limit - 1] + "\u2026"


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
        texts, hidden = [], []
        for page in pages:
            watcher = _PdfHiddenTextWatcher()
            texts.append((page.extract_text(visitor_operand_before=watcher.operand, visitor_text=watcher.text) or "").strip())
            hidden += watcher.snippets()
        text = "\n\n".join(texts)
    except ExtractionError:
        raise
    except Exception:  # pypdf raises many types on malformed input; never leak details
        raise ExtractionError("Could not parse the PDF") from None
    return ExtractionResult(text, "pdf", [EXTRACTION_CAVEAT], hidden)


class _PdfHiddenTextWatcher:
    """Tracks fill colour, text render mode and effective font size while pypdf walks a page's content stream."""

    def __init__(self) -> None:
        self.fill: tuple[str, tuple[float, ...]] = ("g", (0.0,))
        self.render_mode = 0
        self.stack: list[tuple] = []
        self.current: list[str] = []
        self.found: list[str] = []

    def operand(self, op: bytes, args, cm, tm) -> None:
        try:
            if op == b"q":
                self.stack.append((self.fill, self.render_mode))
            elif op == b"Q" and self.stack:
                self.fill, self.render_mode = self.stack.pop()
            elif op in (b"rg", b"g", b"k"):
                self.fill = (op.decode(), tuple(float(a) for a in args))
            elif op == b"Tr" and args:
                self.render_mode = int(args[0])
        except (TypeError, ValueError):
            pass

    def _near_white(self) -> bool:
        kind, values = self.fill
        if kind == "k":  # CMYK: white is all zero
            return all(v <= 1 - _NEAR_WHITE for v in values)
        return bool(values) and all(v >= _NEAR_WHITE for v in values)

    def text(self, text: str, cm, tm, font_dict, font_size) -> None:
        if not text.strip():
            if self.current and "\n" in text:
                self.found.append("".join(self.current))
                self.current = []
            return
        try:
            scale = math.hypot(tm[2], tm[3]) * math.hypot(cm[2], cm[3])
            size = float(font_size) * (scale or 1.0)
        except (TypeError, ValueError, IndexError):
            size = 12.0
        if self.render_mode == 3 or self._near_white() or size <= HIDDEN_MAX_POINTS:
            self.current.append(text)
        elif self.current:
            self.found.append("".join(self.current))
            self.current = []

    def snippets(self) -> list[str]:
        return self.found + (["".join(self.current)] if self.current else [])


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
        paragraphs = list(document.paragraphs)
        for table in document.tables:
            parts += [cell.text for row in table.rows for cell in row.cells]
            paragraphs += [p for row in table.rows for cell in row.cells for p in cell.paragraphs]
        hidden = [h for p in paragraphs for h in _hidden_runs(p)]
    except ExtractionError:
        raise
    except Exception:
        raise ExtractionError("Could not parse the DOCX") from None
    return ExtractionResult("\n".join(parts), "docx", [EXTRACTION_CAVEAT], hidden)


def _hidden_runs(paragraph) -> list[str]:
    """Consecutive runs that are hidden (w:vanish), tiny (<= 2 pt) or near-white, joined per paragraph."""
    out, current = [], []
    for run in paragraph.runs:
        font = run.font
        rgb = font.color.rgb if font.color is not None and font.color.type is not None else None
        white = rgb is not None and all(channel / 255 >= _NEAR_WHITE for channel in (rgb[0], rgb[1], rgb[2]))
        tiny = font.size is not None and font.size.pt <= HIDDEN_MAX_POINTS
        if run.text.strip() and (font.hidden or tiny or white):
            current.append(run.text)
        elif current and run.text.strip():
            out.append("".join(current))
            current = []
    return out + (["".join(current)] if current else [])
