"""FastAPI service for parsing medical PDFs into RAG-ready chunks.

Endpoints
---------
POST /api/v1/parse-pdf   Upload a PDF → get structured JSON chunks
GET  /api/v1/health      Health check
"""

from __future__ import annotations

import time
from typing import List, Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from chunker import chunk_sections
from formatter import format_chunks
from pdf_parser import extract_sections, get_page_count

MAX_UPLOAD_BYTES = 250 * 1024 * 1024  # 250 MB

app = FastAPI(
    title="RAGSYSTEMPDF",
    description="PDF parsing microservice for the Lerini medical RAG system",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/api/v1/health")
async def health():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Parse PDF
# ---------------------------------------------------------------------------

@app.post("/api/v1/parse-pdf")
async def parse_pdf(
    file: UploadFile = File(...),
    category: Optional[str] = Form(None),
    scenario_tags: Optional[str] = Form(None),
    language: Optional[str] = Form("de"),
    chunk_size: Optional[int] = Form(500),
    chunk_overlap: Optional[int] = Form(50),
):
    """Upload a PDF and receive structured JSON chunks for the Unity RAG system.

    Parameters
    ----------
    file : PDF file (multipart upload)
    category : Optional category label (e.g. "Fachsprachprüfung"). Auto-detected if omitted.
    scenario_tags : Optional comma-separated tags (e.g. "anamnese,fsp"). Merged with auto-detected.
    language : Language hint (default "de"). Reserved for future multi-language support.
    chunk_size : Target tokens per chunk (default 500).
    chunk_overlap : Overlap tokens between chunks (default 50).
    """

    # Validate file type
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")

    # Read file with size guard
    pdf_bytes = await file.read()
    if len(pdf_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum is {MAX_UPLOAD_BYTES // (1024*1024)} MB",
        )

    if len(pdf_bytes) == 0:
        raise HTTPException(status_code=400, detail="Empty file")

    start = time.time()

    # Parse tags
    extra_tags: List[str] = []
    if scenario_tags:
        extra_tags = [t.strip() for t in scenario_tags.split(",") if t.strip()]

    # Clamp chunk params
    c_size = max(100, min(2000, chunk_size or 500))
    c_overlap = max(0, min(c_size // 2, chunk_overlap or 50))

    try:
        # Step 1: Extract sections from PDF
        total_pages = get_page_count(pdf_bytes)
        sections = extract_sections(pdf_bytes)

        # Step 2: Chunk sections
        raw_chunks = chunk_sections(sections, max_tokens=c_size, overlap_tokens=c_overlap)

        # Step 3: Format for Unity
        formatted = format_chunks(
            raw_chunks,
            filename=file.filename,
            category=category if category and category.strip() else None,
            extra_tags=extra_tags,
        )

        elapsed = time.time() - start

        return {
            "success": True,
            "chunks": [c.to_dict() for c in formatted],
            "metadata": {
                "filename": file.filename,
                "total_pages": total_pages,
                "total_chunks": len(formatted),
                "chapters_detected": len(sections),
                "processing_time_seconds": round(elapsed, 2),
                "language": language or "de",
                "chunk_size": c_size,
                "chunk_overlap": c_overlap,
            },
        }

    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"PDF processing failed: {exc}")


# ---------------------------------------------------------------------------
# Entrypoint for local dev
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
