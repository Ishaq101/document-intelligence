# Implementation Plan: Document Intelligence System

**Branch**: `001-document-intelligence` | **Date**: 2025-01-15 | **Spec**: [specs/001-document-intelligence/spec.md](specs/001-document-intelligence/spec.md)

**Input**: Feature specification from `/specs/001-document-intelligence/spec.md`

## Summary

Build a document intelligence system with PDF ingestion pipeline, document agent with guardrails/retrieval/generation, and a NextJS frontend. Backend uses FastAPI with Python (uv), PostgreSQL (Neon) for metadata, Qdrant Cloud for vectors, Langfuse for observability. Frontend deployed separately on Vercel.

## Technical Context

**Language/Version**: Python 3.11+ (backend), TypeScript 5+ (frontend)

**Primary Dependencies**: 
- Backend: FastAPI, pydantic, pydantic-settings, llama-parse, pdfplumber, pypdf, openai, qdrant-client, asyncpg/psycopg, langfuse, uvicorn
- Frontend: NextJS 14+, React 18, Tailwind CSS, axios/swagger-client

**Storage**: 
- PostgreSQL (Neon free tier): documents, chunks, chat sessions, messages, eval runs
- Qdrant Cloud (free tier): vector embeddings for chunks

**Testing**: pytest (backend), vitest/jest (frontend), eval runner script

**Target Platform**: Linux containers (Docker), Vercel deployment

**Project Type**: Web application (backend + frontend)

**Performance Goals**: 
- PDF ingestion: 50 pages < 60 seconds
- Agent response: P95 < 10 seconds
- Streaming start: < 2 seconds
- Concurrent uploads: 5 documents

**Constraints**: 
- PDF only, < 50MB
- Free tier limits on Neon, Qdrant, Langfuse
- Single-user demo (admin/123456)
- No caching for MVP

**Scale/Scope**: 
- ~100 documents, ~5000 chunks
- ~1000 chat sessions
- 5-page frontend (login, knowledge, agent, dashboard, admin)

## Constitution Check

No project constitution defined (template only). Proceeding with standard practices.

## Project Structure

### Documentation (this feature)

```text
specs/001-document-intelligence/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output (OpenAPI spec)
└── tasks.md             # Phase 2 output (/speckit-tasks command)
```

### Source Code (repository root)

```text
service-docintel/           # Backend (FastAPI)
├── app/
│   ├── main.py             # FastAPI app + routes
│   ├── config.py           # Settings from env
│   ├── models/             # Pydantic models (DB, API, Agent)
│   ├── services/           # Business logic
│   │   ├── ingestion/      # Parser, chunker, embedder, pipeline
│   │   ├── agent/          # Guardrails, intent, tasks, retrieval, generation, review
│   │   ├── storage/        # Postgres, Qdrant clients
│   │   └── observability/  # Langfuse helpers
│   └── api/                # API route modules
├── evals/
│   └── run_eval.py         # Evaluation runner
├── tests/
├── pyproject.toml          # uv project config
├── Dockerfile
└── .env

frontend/                   # Frontend (NextJS)
├── app/
│   ├── login/page.tsx
│   ├── knowledge/page.tsx
│   ├── agent/page.tsx
│   ├── dashboard/page.tsx
│   └── admin/page.tsx
├── components/
├── lib/
├── package.json
├── Dockerfile
└── .env.local
```

**Structure Decision**: Option 2 (Web application) — separate `service-docintel/` backend and `frontend/` directories, each with own Dockerfile for independent Vercel deployment.

## Complexity Tracking

No violations — straightforward two-service architecture matching spec requirements.

---

## Phase 0: Research

### Unknowns to Resolve

1. **LlamaParse integration pattern** — sync vs async, error handling, quota detection
2. **Hybrid RRF implementation** — BM25 (PostgreSQL full-text) + Qdrant vector search combining via RRF
3. **Structured output with citations** — Pydantic model design for LLM response with citation fields
4. **Langfuse span/trace pattern** — trace per chat, spans for guardrails/intent/retrieval/generation/review
5. **Streaming response format** — Server-Sent Events vs WebSocket, token-by-token vs chunked
6. **Admin config persistence** — where to store chunk_size, overlap, retrieval_method, top_k (DB vs file)

### Research Tasks

```text
Task 1: Research LlamaParse Python SDK best practices for async page-by-page parsing with fallback handling
Task 2: Research hybrid BM25+vector RRF implementation patterns in Python (PostgreSQL tsvector + Qdrant)
Task 3: Research Pydantic structured output for LLM citations (OpenAI function calling / response_format)
Task 4: Research Langfuse Python SDK trace/span patterns for multi-step agent flows
Task 5: Research FastAPI streaming response patterns (SSE) for token streaming
Task 6: Research NextJS streaming chat UI patterns (ChatGPT-like interactive buffer)
```

### Research Output: `research.md`

Will document decisions for each unknown with code snippets.

---

## Phase 1: Design

### Data Model (`data-model.md`)

Define entities from spec:
- Document (file_id, filename, status, page_count, upload_timestamp, file_size)
- Chunk (chunk_id, file_id, filename, page, category, company, content, vector_content)
- ChatSession (session_id, user_id, trace_id, created_at)
- Message (message_id, session_id, role, content, citations, runtime_ms, timestamp)
- EvalTestCase (test_case_id, category, question, expected_result)
- AdminConfig (chunk_size, chunk_overlap, retrieval_method, top_k)

PostgreSQL schema with indexes for filterable fields (filename, file_id, page, category, company).
Qdrant collection schema with payload indexes for same filterable fields.

### API Contracts (`contracts/`)

OpenAPI 3.0 spec for:
- POST /documents/upload — multipart file upload
- POST /documents/{file_id}/process — trigger ingestion
- GET /documents — list with status
- DELETE /documents/{file_id} — delete document
- POST /chat — streaming chat endpoint (SSE)
- GET /chat/sessions — list sessions
- GET /dashboard/stats — dashboard metrics
- GET /admin/config — get admin config
- PUT /admin/config — update admin config
- POST /eval/run — trigger evaluation

### Quickstart (`quickstart.md`)

Steps to run locally:
1. Copy `.env.example` to `.env` and fill keys
2. `cd service-docintel && uv sync && uv run uvicorn app.main:app --reload`
3. `cd frontend && npm install && npm run dev`
4. Visit http://localhost:3000, login admin/123456
5. Upload PDF, process, chat

---

## Phase 2: Implementation Order (for `/speckit-tasks`)

### Backend Foundation
1. Config & settings (pydantic-settings from env)
2. PostgreSQL models + async connection pool
3. Qdrant client + collection setup
4. Langfuse client + trace/span helpers
5. API routes skeleton with health check

### Ingestion Pipeline
6. Parser routing (LlamaParse/pdfplumber/pypdf per page type)
7. Page chunker (configurable size/overlap)
8. Embedder (text-embedding-3-small via OpenAI)
9. Pipeline orchestration + status tracking
10. Upload/process/delete API endpoints

### Agent Core
11. Guardrails (PII, injection, NSFW, unsafe chars, language)
12. Intent classification (need_plan, social_question)
13. Task implementations (metadata, retrieval, summary)
14. Hybrid retrieval (BM25 + vector RRF, top-k)
15. Evidence evaluation (sufficient/not_sufficient/not_relevant)
16. Generator (structured output + citations, streaming)
17. Review (correctness, grounded, clean_format, PII)
18. Main agent flow orchestration
19. Chat API endpoint (SSE streaming)

### Observability & Eval
20. Langfuse integration in agent flow
21. Runtime logging to PostgreSQL
22. Eval runner against eval_dataset.jsonl

### Frontend
23. NextJS project setup + Tailwind (color palette)
24. Login page (admin/123456)
25. Knowledge page (upload, list, process, delete)
26. Agent page (streaming chat, citations, waiting buffer)
27. Dashboard page (stats, runtime metrics)
28. Admin page (config form)

### Deployment
29. Backend Dockerfile
30. Frontend Dockerfile
31. Docker Compose for local dev
32. Vercel deployment configs

---

## Phase 3: Verification

- Unit tests for parser routing, chunking, retrieval, guardrails
- Integration tests for ingestion pipeline, agent flow
- Contract tests for API endpoints
- Eval runner passes spec eval_dataset.jsonl
- Manual smoke test: upload → process → chat → dashboard → admin

---

*Generated by `/speckit-plan` — ready for `/speckit-tasks`*