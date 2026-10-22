# Document Intelligence

Document Intelligence helps users find relevant information from uploaded PDF documents. Backend currently supports document upload, ingestion, retrieval, and chat APIs.

## Capability and Limitation

### Current capability

- Upload PDF files up to 50 MB. Duplicate filenames are rejected per demo user.
- Admin must create a category before upload; each document uses one existing category.
- Store source PDFs in Supabase S3-compatible storage, document metadata and chunks in PostgreSQL, and dense plus sparse vectors in Qdrant.
- Parse pages by detected content. A page containing both table and image content is treated as an image page.
- Retrieve with dense vector search, sparse search, or hybrid Reciprocal Rank Fusion (RRF). Hybrid RRF is default.
- Generate chat responses with retrieved-document citations. Streaming endpoint is available.
- Admin API can manage categories and retrieval settings, and remove all uploaded demo documents and vectors.

### Known limitation

- Single-user demo only. No real login, authorization, or multi-user data isolation.
- Frontend screens are not implemented yet.
- No background queue or retry mechanism for ingestion and cleanup.
- Source PDF cleanup can fail independently; cleanup response reports `failed_source_deletions`.
- Dashboard evaluation-run endpoint needs schema validation.
- Deployment configuration is not available yet.

## Evaluation Method and Result

Evaluation uses 20 directed cases from [`service-docintel/evals/datasets/eval_dataset.jsonl`](service-docintel/evals/datasets/eval_dataset.jsonl). The cases cover document metadata, factual, table, visual, glossary, conflict-resolution, multi-hop, and abstention scenarios.

The runner talks to a running backend through `POST /chat`. Each case starts an independent chat session, then `gpt-6-luna` judges the response against expected facts and citations. It records:

- Correctness: 30%
- Completeness: 25%
- Groundedness: 30%
- Citation accuracy: 15%

Run from `service-docintel/` after starting the backend:

```bash
uv run python evals/run_eval.py
```

Each run writes a conversation log as JSONL and a report as Markdown under `service-docintel/evals/results/`. Generated results are local artifacts and are not committed.

The latest recorded run from October 22, 2026 (21:48 UTC) scored **0.765** weighted across 20 cases, up from the prior 0.631 baseline. This is an internal development baseline, not a production benchmark or pass result; no pass/fail threshold is defined yet. Aggregate metrics for the latest run:

| Metric | Mean score |
|---|---:|
| Correctness | 0.766 |
| Completeness | 0.761 |
| Groundedness | 0.705 |
| Citation Accuracy | 0.887 |
| Weighted score | 0.765 |

Citation accuracy is the strongest dimension (0.887); groundedness is the weakest (0.705), driven by answers that add details not established by the cited facts. Known extraction gaps remain on visual facts embedded in charts, cards, and image tables, so several visual/table cases (TC-007, TC-009) underperform and are expected to improve with visual extraction. The full per-case breakdown is in the generated report under `service-docintel/evals/results/`.

## How To Run

### Backend

1. Copy environment template and fill required service credentials:
   ```bash
   cp service-docintel/.env.example service-docintel/.env
   ```
2. Install Python dependencies:
   ```bash
   uv --directory service-docintel sync
   ```
3. Start API on port 8010:
   ```bash
   uv --directory service-docintel run uvicorn app.main:app --reload --port 8010
   ```
4. Verify health endpoint:
   ```bash
   curl -sS http://localhost:8010/health
   ```
5. Open API documentation:
   ```bash
   start http://localhost:8010/docs
   ```

### Frontend

1. Open frontend directory:
   ```bash
   cd frontend
   ```
2. Install dependencies:
   ```bash
   npm install
   ```
3. Start frontend on port 3010:
   ```bash
   npm run dev
   ```
4. Open frontend URL:
   ```bash
   start http://localhost:3010
   ```
5. <!-- TODO: Add frontend environment setup and user-flow verification after frontend implementation. -->

## Architecture Overview

```text
Client
  |
  v
FastAPI backend (service-docintel, port 8010)
  |
  +-- PostgreSQL: documents, chunks, chat sessions, messages, admin settings
  +-- Qdrant: dense and sparse chunk vectors
  +-- Supabase S3-compatible storage: original PDFs
  +-- LlamaParse / pdfplumber / pypdf: page extraction
  +-- OpenAI-compatible API: embeddings and answer generation
  +-- Langfuse: chat trace and sub-process spans
```

### Key Decision and Trade-off

- **Separate stores by purpose.** PostgreSQL stores records, Qdrant supports retrieval, and object storage retains source PDFs. Deletion must coordinate across all three.
- **Page-level chunks.** Preserves page citations and simpler inspection. Context across pages can be weaker.
- **Hybrid retrieval default.** Combines dense and sparse results with RRF. Better coverage than one retrieval method, but needs evaluation before quality claims.
- **Shared database pool.** PostgreSQL connections use a shared async pool and request-scoped acquisition. External-service retry and queue handling are not available yet.

### Room for Improvement

- Build frontend flows for knowledge management, chat, dashboard, and admin configuration.
- Add authentication, authorization, and user ID filters for Qdrant retrieval.
- Add automated tests, improve evaluation coverage, and define a reviewed quality threshold.
- Move ingestion and cleanup into retriable background jobs.
- Add Docker and deployment configuration.

## API Notes

- Interactive docs: `http://localhost:8010/docs`
- Health: `GET /health`
- Documents: `/documents`
- Chat: `/chat` and `/chat/stream`
- Dashboard: `/dashboard`
- Admin: `/admin`

Bulk cleanup is destructive:

```bash
curl -sS -X DELETE http://localhost:8010/admin/documents
```

This removes demo-user document rows, PostgreSQL chunks, Qdrant vectors, and stored source PDFs. Categories and admin settings remain. Check `failed_source_deletions` in response.

## How I Use AI to Help Me Build This Project

I first wrote [SPECIFICATION.md](docs/SPECIFICATION.md) by hand. Then I used a specification-driven workflow to review requirements, create planning artifacts, break work into tasks, implement, and smoke-test backend flows. I used manual approval for code changes. AI-assisted work does not replace review, testing, or validation.

## For Customer
Please read [README-CUSTOMER.md](README-CUSTOMER.md) to get product overview for business owner or non technical customer.