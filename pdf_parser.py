"""PDF text extraction with chapter/section detection using pymupdf (fitz).

Optimised for German medical textbooks (Fachsprachprüfung books).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List

import fitz  # pymupdf


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class Section:
    """A detected section/chapter from the PDF."""
    title: str
    content: str
    page_start: int        # 1-based
    page_end: int          # 1-based
    level: int = 1         # 1 = chapter, 2 = section, 3 = subsection
    children: List["Section"] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Header detection heuristics
# ---------------------------------------------------------------------------

# German chapter/section numbering patterns
_CHAPTER_RE = re.compile(
    r"^(?:"
    r"(?:Kapitel|KAPITEL|Teil|TEIL|Abschnitt|ABSCHNITT)\s+\d+"  # "Kapitel 1"
    r"|(?:TEIL\s+[IVXLCDM]+)"                                   # "TEIL III"
    r"|\d{1,2}(?:\.\d{1,2}){0,3}(?:\s)"                         # "1. ", "1.2 ", "3.2.1 "
    r")",
    re.MULTILINE,
)

_ALL_CAPS_RE = re.compile(r"^[A-ZÄÖÜ\s\-:]{8,}$")


def _is_likely_heading(text: str, font_size: float, avg_font: float, is_bold: bool) -> int:
    """Return heading level (1-3) or 0 if not a heading."""
    text = text.strip()
    if not text or len(text) > 200:
        return 0

    # Large font = chapter heading
    if font_size >= avg_font * 1.4:
        if _CHAPTER_RE.match(text) or _ALL_CAPS_RE.match(text):
            return 1
        return 2 if font_size >= avg_font * 1.2 else 0

    # Bold numbered heading
    if is_bold and _CHAPTER_RE.match(text):
        if re.match(r"^\d{1,2}\.\d", text):
            return 3  # subsection  "1.2 ..."
        return 2      # section     "1. ..."

    # ALL-CAPS block (sometimes used for chapter titles)
    if _ALL_CAPS_RE.match(text) and is_bold:
        return 1

    return 0


# ---------------------------------------------------------------------------
# Span-level analysis helpers
# ---------------------------------------------------------------------------

def _analyse_page_spans(page: fitz.Page):
    """Yield (text, font_size, is_bold) per text block from raw spans."""
    blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]
    for block in blocks:
        if block.get("type") != 0:  # text block
            continue
        for line in block.get("lines", []):
            line_text_parts: list[str] = []
            sizes: list[float] = []
            bold_count = 0
            for span in line.get("spans", []):
                t = span.get("text", "")
                if not t.strip():
                    continue
                line_text_parts.append(t)
                sizes.append(span.get("size", 12.0))
                if "bold" in span.get("font", "").lower():
                    bold_count += 1

            if not line_text_parts:
                continue

            text = "".join(line_text_parts)
            avg_size = sum(sizes) / len(sizes) if sizes else 12.0
            is_bold = bold_count > len(line_text_parts) / 2
            yield text, avg_size, is_bold


# ---------------------------------------------------------------------------
# Main extraction
# ---------------------------------------------------------------------------

def extract_sections(pdf_bytes: bytes) -> List[Section]:
    """Parse a PDF and return a flat list of sections with content."""

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    total_pages = len(doc)

    # First pass: compute average body font size across first 20 pages
    all_sizes: list[float] = []
    sample_pages = min(20, total_pages)
    for i in range(sample_pages):
        for _, size, _ in _analyse_page_spans(doc[i]):
            all_sizes.append(size)
    avg_font = sum(all_sizes) / len(all_sizes) if all_sizes else 12.0

    # Second pass: extract sections
    sections: List[Section] = []
    current_title = "Introduction"
    current_content_parts: list[str] = []
    current_page_start = 1
    current_level = 1

    for page_idx in range(total_pages):
        page = doc[page_idx]
        page_num = page_idx + 1

        for text, font_size, is_bold in _analyse_page_spans(page):
            heading_level = _is_likely_heading(text, font_size, avg_font, is_bold)

            if heading_level > 0:
                # Save previous section
                body = "\n".join(current_content_parts).strip()
                if body:
                    sections.append(Section(
                        title=current_title,
                        content=body,
                        page_start=current_page_start,
                        page_end=page_num,
                        level=current_level,
                    ))

                # Start new section
                current_title = text.strip()
                current_content_parts = []
                current_page_start = page_num
                current_level = heading_level
            else:
                current_content_parts.append(text)

    # Flush last section
    body = "\n".join(current_content_parts).strip()
    if body:
        sections.append(Section(
            title=current_title,
            content=body,
            page_start=current_page_start,
            page_end=total_pages,
            level=current_level,
        ))

    doc.close()
    return sections


def get_page_count(pdf_bytes: bytes) -> int:
    """Return total number of pages without full extraction."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    count = len(doc)
    doc.close()
    return count
