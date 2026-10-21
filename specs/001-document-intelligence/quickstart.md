# Quickstart: Document Intelligence System

**Feature**: Document Intelligence System  
**Date**: 2025-01-15

---

## Prerequisites

- Python 3.11+ with `uv` installed
- Node.js 18+ with `npm`
- Neon PostgreSQL account (free tier)
- Qdrant Cloud account (free tier)
- Langfuse account (free tier)
- OpenAI API key (for GPT-6 Luna + text-embedding-3-small)
- LlamaParse API key
- (Optional) PaddleOCR API key for future fallback

---

## Environment Setup

### 1. Backend Environment

```bash
cd service-docintel
cp .env.example .env
# Edit .env with your keys:
# OPENAI_API_KEY=sk-...
# LLAMAPARSE_API_KEY=llx-...
# PADDLE_OCR_API_KEY=... (optional)
# LANGFUSE_PUBLIC_KEY=pk-lf-...
# LANGFUSE_SECRET_KEY=sk-lf-...
# LANGFUSE_BASE_URL=https://us.cloud.langfuse.com
# POSTGRES_CONNSTRING=postgresql://user:pass@host/db?sslmode=require
# QDRANT_API_KEY=...
# QDRANT_ENDPOINT=https://xxx.us-west-2-0.aws.cloud.qdrant.io
```

### 2. Frontend Environment

```bash
cd frontend
cp .env.example .env.local
# Edit .env.local:
# NEXT_PUBLIC_API_URL=http://localhost:8000
```

---

## Database Initialization

Run migrations to create tables:

```bash
cd service-docintel
uv run python -m app.db.init_db
```

This creates:
- `documents`, `chunks`, `chat_sessions`, `messages`, `admin_config`, `eval_runs` tables
- Qdrant collection `document_chunks` with vector index and payload indexes

---

## Running Locally

### Terminal 1: Backend (FastAPI)

```bash
cd service-docintel
uv sync
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

API docs at: http://localhost:8000/docs

### Terminal 2: Frontend (NextJS)

```bash
cd frontend
npm install
npm run dev
```

Frontend at: http://localhost:3000

---

## First Time Setup

1. **Visit** http://localhost:3000
2. **Login** with seed credentials:
   - Username: `admin`
   - Password: `123456`
   - User ID: `00000000-0000-0000-0000-000000000001` (fixed UUID for seed user)
3. **Upload a PDF** on Knowledge page (drag & drop or click)
4. **Click "Process"** to run ingestion pipeline
5. **Wait for status** to show "completed"
6. **Go to Agent page** and ask questions

---

## API Usage Examples

### Upload Document

```bash
curl -X POST http://localhost:8000/documents/upload \
  -F "file=@sample.pdf"
```

Response:
```json
{
  "file_id": "uuid",
  "filename": "sample.pdf",
  "status": "pending",
  "page_count": 0,
  "file_size_bytes": 123456,
  "upload_timestamp": "2025-01-15T10:30:00Z"
}
```

### Process Document

```bash
curl -X POST http://localhost:8000/documents/{file_id}/process
```

### List Documents

```bash
curl http://localhost:8000/documents
```

### Chat (Streaming)

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "What is the revenue for 2025?"}' \
  --no-buffer
```

Response (SSE):
```
data: {"type": "start", "session_id": "uuid"}

data: {"type": "token", "content": "The"}

data: {"type": "token", "content": " revenue"}

data: {"type": "token", "content": " for 2025"}

data: {"type": "citations", "citations": [{"filename": "sample.pdf", "page": 3, "chunk_id": "uuid"}]}

data: {"type": "done", "runtime_ms": 1234}
```

### Dashboard Stats

```bash
curl http://localhost:8000/dashboard/stats
```

### Admin Config

```bash
# Get current config
curl http://localhost:8000/admin/config

# Update config
curl -X PUT http://localhost:8000/admin/config \
  -H "Content-Type: application/json" \
  -d '{"chunk_size": 2, "top_k": 10}'
```

### Run Evaluation

```bash
cd service-docintel
uv run python -m evals.run_eval
```

---

## Docker Deployment

### Build Images

```bash
# Backend
cd service-docintel
docker build -t document-intelligence-backend .

# Frontend
cd ../frontend
docker build -t document-intelligence-frontend .
```

### Run with Docker Compose

```yaml
# docker-compose.yml (at repo root)
version: '3.8'
services:
  backend:
    image: document-intelligence-backend
    ports:
      - "8000:8000"
    env_file:
      - service-docintel/.env
    depends_on:
      - postgres  # if running local PG
  
  frontend:
    image: document-intelligence-frontend
    ports:
      - "3000:3000"
    env_file:
      - frontend/.env.local
    depends_on:
      - backend
```

```bash
docker-compose up -d
```

---

## Vercel Deployment

### Backend (separate Vercel project)

1. Connect `service-docintel` folder to Vercel
2. Set environment variables in Vercel dashboard
3. Deploy — Vercel detects FastAPI via `vercel.json`

### Frontend (separate Vercel project)

1. Connect `frontend` folder to Vercel
2. Set `NEXT_PUBLIC_API_URL` to backend Vercel URL
3. Deploy

---

## Project Structure Reference

```
document-intelligence/
├── service-docintel/           # Backend
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── models/
│   │   ├── services/
│   │   │   ├── ingestion/
│   │   │   ├── agent/
│   │   │   ├── storage/
│   │   │   └── observability/
│   │   └── api/
│   ├── evals/
│   ├── tests/
│   ├── pyproject.toml
│   ├── Dockerfile
│   └── .env
├── frontend/                   # Frontend
│   ├── app/
│   ├── components/
│   ├── lib/
│   ├── package.json
│   ├── Dockerfile
│   └── .env.local
├── specs/001-document-intelligence/
│   ├── spec.md
│   ├── plan.md
│   ├── research.md
│   ├── data-model.md
│   ├── quickstart.md
│   ├── contracts/
│   └── tasks.md
└── docker-compose.yml
```

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "relation documents does not exist" | Run `uv run python -m app.db.init_db` |
| "Qdrant collection not found" | Check `QDRANT_ENDPOINT` and API key; run init script |
| "Langfuse connection failed" | Verify `LANGFUSE_BASE_URL`, keys; check network |
| "LlamaParse quota exceeded" | Check API key; wait for reset; PaddleOCR not implemented yet |
| Frontend can't connect to backend | Verify `NEXT_PUBLIC_API_URL`; check CORS in `main.py` |
| Streaming not working | Disable nginx buffering (`X-Accel-Buffering: no`); check SSE format |

---

## Next Steps

1. Run `/speckit-tasks` to generate detailed implementation tasks
2. Implement backend foundation (config, DB, Qdrant, Langfuse)
3. Build ingestion pipeline
4. Build agent core
5. Build frontend pages
6. Run evals and iterate