# RAGSYSTEMPDF

PDF parsing microservice for the **Lerini** medical RAG system. Accepts PDF uploads (e.g. German medical textbooks) and returns structured, chunked JSON ready for embedding and vector storage in the Unity client.

## Quick start (local)

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Set your API key
export API_KEY="your-secret-key"

# 3. Run the server
uvicorn app:app --reload --port 8000
```

Open http://localhost:8000/docs for the interactive Swagger UI.

## API

### `GET /api/v1/health`

Health check — no auth required.

```bash
curl http://localhost:8000/api/v1/health
# {"status":"ok"}
```

### `POST /api/v1/parse-pdf`

Upload a PDF and receive structured JSON chunks.

**Headers:** `X-API-Key: <your key>`

**Form fields:**

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `file` | PDF file | yes | — | The PDF to parse |
| `category` | string | no | auto-detect | Category label (e.g. "Fachsprachprüfung") |
| `scenario_tags` | string | no | auto-detect | Comma-separated tags (e.g. "anamnese,fsp") |
| `language` | string | no | `de` | Language hint |
| `chunk_size` | int | no | `500` | Target tokens per chunk |
| `chunk_overlap` | int | no | `50` | Overlap tokens between chunks |

**Example:**

```bash
curl -X POST http://localhost:8000/api/v1/parse-pdf \
  -H "X-API-Key: your-secret-key" \
  -F "file=@my_medical_book.pdf" \
  -F "category=Fachsprachprüfung" \
  -F "scenario_tags=anamnese,fsp,medical_german"
```

**Response:**

```json
{
  "success": true,
  "chunks": [
    {
      "document_id": "my_medical_book_ch0001",
      "category": "Fachsprachprüfung",
      "scenario_tags": ["anamnese", "fsp", "medical_german", "patient_history"],
      "clinical_context": "Kapitel 1 — Anamnesegespräch",
      "section_title": "Anamnesegespräch",
      "content": "Die Anamnese ist das wichtigste diagnostische Werkzeug...",
      "token_count": 487,
      "page_start": 12,
      "page_end": 13
    }
  ],
  "metadata": {
    "filename": "my_medical_book.pdf",
    "total_pages": 450,
    "total_chunks": 892,
    "chapters_detected": 15,
    "processing_time_seconds": 28.3,
    "language": "de",
    "chunk_size": 500,
    "chunk_overlap": 50
  }
}
```

## Deploy to Render.com

1. Push this repo to GitHub
2. Create a new **Web Service** on Render
3. Connect your GitHub repo
4. Set environment variable: `API_KEY` = your secret key
5. Render will auto-detect `render.yaml` and deploy

## Architecture

```
PDF Upload
    ↓
pdf_parser.py    → Extract text + detect chapters/sections (pymupdf)
    ↓
chunker.py       → Split sections into ~500-token chunks with overlap
    ↓
formatter.py     → Add document IDs, auto-detect German medical tags, format JSON
    ↓
JSON Response    → Unity client embeds chunks locally + stores in VectorDatabase
```

## German Medical Tag Detection

The formatter automatically detects German medical terms and maps them to scenario tags:

| German Term | Generated Tags |
|-------------|----------------|
| Anamnese | `anamnese`, `patient_history` |
| Therapie | `therapy`, `treatment` |
| Diagnose | `diagnosis`, `differential_diagnosis` |
| Untersuchung | `examination`, `physical_exam` |
| Kardiologie | `cardiology`, `cardiovascular` |
| Neurologie | `neurology` |
| Fachsprachprüfung | `fsp`, `medical_german` |
| Arztbrief | `medical_letter`, `documentation` |
| ... | (80+ mappings) |

## License

Private — Lerini project.
