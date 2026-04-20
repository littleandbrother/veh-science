"""PDF ingestion helpers for replay mode."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from pypdf import PdfReader


_HEADING_PATTERN = re.compile(r"^(?:\d+(?:\.\d+)*)\s+[A-Z][^\n]{2,}$")


def extract_pdf_pages(path: str | Path) -> list[str]:
    """Extract plain text page-by-page from a PDF."""

    reader = PdfReader(str(path))
    pages: list[str] = []
    for page in reader.pages:
        text = page.extract_text() or ""
        pages.append(text)
    return pages


def extract_pdf_text(path: str | Path) -> str:
    return "\n\n".join(extract_pdf_pages(path))


def extract_section_map(pages: list[str]) -> dict[str, list[str]]:
    """Build a coarse section map from page text.

    The function is intentionally lightweight. It uses numbered headings when
    present and otherwise falls back to a single ``Document`` section.
    """

    sections: dict[str, list[str]] = {}
    current = "Document"
    for page_index, page_text in enumerate(pages, start=1):
        lines = [line.strip() for line in page_text.splitlines() if line.strip()]
        buffer: list[str] = []
        for line in lines:
            if _HEADING_PATTERN.match(line) or line.startswith("Appendix"):
                if buffer:
                    sections.setdefault(current, []).append(" ".join(buffer))
                    buffer = []
                current = f"p{page_index}: {line}"
                sections.setdefault(current, [])
            else:
                buffer.append(line)
        if buffer:
            sections.setdefault(current, []).append(" ".join(buffer))
    return sections


def sentence_candidates(text: str) -> list[str]:
    """Split a document into manageable sentence-like candidates."""

    normalized = re.sub(r"\s+", " ", text).strip()
    if not normalized:
        return []
    fragments = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", normalized)
    return [fragment.strip() for fragment in fragments if len(fragment.strip()) > 40]


def keyword_matches(sentences: list[str], keywords: tuple[str, ...], limit: int = 4) -> list[str]:
    """Return up to *limit* sentences covering *keywords*."""

    lowered = [(sentence, sentence.lower()) for sentence in sentences]
    ranked: list[tuple[int, str]] = []
    for sentence, lower in lowered:
        score = sum(1 for keyword in keywords if keyword.lower() in lower)
        if score > 0:
            ranked.append((score, sentence))
    ranked.sort(key=lambda item: (-item[0], len(item[1])))
    selected: list[str] = []
    seen: set[str] = set()
    for _, sentence in ranked:
        if sentence in seen:
            continue
        selected.append(sentence)
        seen.add(sentence)
        if len(selected) >= limit:
            break
    return selected


def build_pdf_digest(path: str | Path) -> dict[str, Any]:
    pages = extract_pdf_pages(path)
    text = "\n\n".join(pages)
    sections = extract_section_map(pages)
    preview = text[:3000]
    return {
        "path": str(Path(path).resolve()),
        "n_pages": len(pages),
        "section_titles": list(sections.keys())[:16],
        "preview": preview,
    }
