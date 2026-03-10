"""Section-aware text chunking for medical knowledge.

Splits by section boundaries first, then sub-chunks large sections
by sentence boundaries with configurable overlap.  Token estimation
uses len(text)/4 to match the Unity client.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List

from pdf_parser import Section

DEFAULT_CHUNK_SIZE = 500     # target tokens per chunk
DEFAULT_CHUNK_OVERLAP = 50   # overlap tokens between consecutive sub-chunks

# Sentence-ending pattern (handles German abbreviations like "z.B." gracefully)
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def estimate_tokens(text: str) -> int:
    """Estimate token count (matches Unity's Mathf.CeilToInt(len/4))."""
    return max(1, -(-len(text) // 4))  # ceiling division


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

@dataclass
class RawChunk:
    """An intermediate chunk before final formatting."""
    text: str
    section_title: str
    parent_chapter: str
    page_start: int
    page_end: int
    token_count: int


# ---------------------------------------------------------------------------
# Chunking logic
# ---------------------------------------------------------------------------

def _split_sentences(text: str) -> List[str]:
    """Split text into sentences while preserving content."""
    parts = _SENTENCE_END.split(text)
    return [s for s in parts if s.strip()]


def _sub_chunk(
    text: str,
    section_title: str,
    parent_chapter: str,
    page_start: int,
    page_end: int,
    max_tokens: int,
    overlap_tokens: int,
) -> List[RawChunk]:
    """Break a large text block into overlapping sub-chunks by sentence."""

    sentences = _split_sentences(text)
    if not sentences:
        return []

    chunks: List[RawChunk] = []
    current_sentences: list[str] = []
    current_tokens = 0

    for sent in sentences:
        sent_tokens = estimate_tokens(sent)

        if current_tokens + sent_tokens > max_tokens and current_sentences:
            chunk_text = " ".join(current_sentences)
            chunks.append(RawChunk(
                text=chunk_text,
                section_title=section_title,
                parent_chapter=parent_chapter,
                page_start=page_start,
                page_end=page_end,
                token_count=estimate_tokens(chunk_text),
            ))

            # Keep overlap: walk backwards to collect ~overlap_tokens
            overlap_sents: list[str] = []
            overlap_tok = 0
            for s in reversed(current_sentences):
                st = estimate_tokens(s)
                if overlap_tok + st > overlap_tokens:
                    break
                overlap_sents.insert(0, s)
                overlap_tok += st

            current_sentences = overlap_sents
            current_tokens = overlap_tok

        current_sentences.append(sent)
        current_tokens += sent_tokens

    # Flush remaining
    if current_sentences:
        chunk_text = " ".join(current_sentences)
        chunks.append(RawChunk(
            text=chunk_text,
            section_title=section_title,
            parent_chapter=parent_chapter,
            page_start=page_start,
            page_end=page_end,
            token_count=estimate_tokens(chunk_text),
        ))

    return chunks


def chunk_sections(
    sections: List[Section],
    max_tokens: int = DEFAULT_CHUNK_SIZE,
    overlap_tokens: int = DEFAULT_CHUNK_OVERLAP,
) -> List[RawChunk]:
    """Convert parsed PDF sections into RAG-ready chunks.

    Sections that fit within *max_tokens* are kept whole.
    Larger sections are split by sentence with *overlap_tokens* overlap.
    """

    chunks: List[RawChunk] = []

    # Track the most recent level-1 heading as "parent chapter"
    current_chapter = ""

    for section in sections:
        if section.level == 1:
            current_chapter = section.title

        tokens = estimate_tokens(section.content)

        if tokens <= max_tokens:
            chunks.append(RawChunk(
                text=section.content,
                section_title=section.title,
                parent_chapter=current_chapter or section.title,
                page_start=section.page_start,
                page_end=section.page_end,
                token_count=tokens,
            ))
        else:
            sub = _sub_chunk(
                section.content,
                section_title=section.title,
                parent_chapter=current_chapter or section.title,
                page_start=section.page_start,
                page_end=section.page_end,
                max_tokens=max_tokens,
                overlap_tokens=overlap_tokens,
            )
            chunks.extend(sub)

    return chunks
