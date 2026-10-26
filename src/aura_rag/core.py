from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from io import BytesIO


CHUNKER_VERSION = "page-char-overlap-v1"
CHUNK_SIZE = 900
CHUNK_OVERLAP = 120


class PdfIngestionError(ValueError):
    """A user-correctable PDF ingestion problem."""


@dataclass(frozen=True)
class PageText:
    page_number: int
    text: str


@dataclass(frozen=True)
class TextChunk:
    index: int
    text: str
    page_start: int | None
    page_end: int | None
    content_sha256: str


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def parse_pdf(content: bytes) -> tuple[list[PageText], list[int]]:
    if not content.startswith(b"%PDF-"):
        raise PdfIngestionError("The uploaded file is not a PDF (missing PDF signature).")
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise PdfIngestionError("PDF parsing is unavailable; install the documented RAG dependencies.") from exc

    try:
        reader = PdfReader(BytesIO(content), strict=True)
        if reader.is_encrypted:
            raise PdfIngestionError("This PDF is encrypted or password-protected; provide an unlocked PDF.")
        pages = []
        empty_pages = []
        for page_number, page in enumerate(reader.pages, start=1):
            raw_text = page.extract_text() or ""
            normalized = re.sub(r"[ \t]+", " ", raw_text)
            normalized = re.sub(r"\n[ \t]*\n[ \t]*\n+", "\n\n", normalized).strip()
            if normalized:
                pages.append(PageText(page_number, normalized))
            else:
                empty_pages.append(page_number)
        if not len(reader.pages):
            raise PdfIngestionError("The PDF contains no pages.")
        return pages, empty_pages
    except PdfIngestionError:
        raise
    except Exception as exc:
        raise PdfIngestionError("The PDF could not be read; verify that it is not corrupt.") from exc


def chunk_pages(pages: list[PageText]) -> list[TextChunk]:
    chunks: list[TextChunk] = []
    for page in pages:
        start = 0
        text = page.text
        while start < len(text):
            end = min(start + CHUNK_SIZE, len(text))
            if end < len(text):
                boundary = text.rfind(" ", start, end)
                if boundary > start + CHUNK_SIZE // 2:
                    end = boundary
            body = text[start:end].strip()
            if body:
                digest = sha256_bytes(body.encode("utf-8"))
                chunks.append(TextChunk(len(chunks), body, page.page_number, page.page_number, digest))
            if end >= len(text):
                break
            start = max(start + 1, end - CHUNK_OVERLAP)
    return chunks


def lexical_score(query: str, text: str) -> float:
    query_terms = _terms(query)
    if not query_terms:
        return 0.0
    evidence_terms = set(_terms(text))
    matched = sum(1 for term in query_terms if term in evidence_terms)
    return matched / len(query_terms)


def _terms(text: str) -> list[str]:
    stop_words = {
        "a", "an", "and", "are", "at", "by", "for", "from", "how", "i", "in",
        "is", "it", "of", "on", "or", "the", "to", "was", "what", "when",
        "where", "which", "who", "with",
    }
    tokens = []
    for token in re.findall(r"[a-z0-9]+", text.casefold()):
        if token.endswith("ies") and len(token) > 4:
            token = token[:-3] + "y"
        elif token.endswith("s") and len(token) > 3:
            token = token[:-1]
        if token not in stop_words:
            tokens.append(token)
    return list(dict.fromkeys(tokens))
