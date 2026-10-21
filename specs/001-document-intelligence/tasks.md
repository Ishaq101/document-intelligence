---
description: "Task list for Document Intelligence System implementation"
---

# Tasks: Document Intelligence System

**Input**: Design documents from `/specs/001-document-intelligence/`

**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Tests**: The examples below include test tasks. Tests are OPTIONAL - only include them if explicitly requested in the feature specification.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **Web app**: `service-docintel/` (backend), `frontend/` (frontend)
- Paths shown below use the structure from plan.md

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and basic structure for both backend and frontend

- [ ] T001 Create backend project structure per implementation plan (`service-docintel/`)
- [ ] T002 Create frontend project structure per implementation plan (`frontend/`)
- [ ] T003 [P] Initialize Python project with uv in `service-docintel/pyproject.toml`
- [ ] T004 [P] Initialize NextJS project with npm in `frontend/package.json`
- [ ] T005 [P] Configure linting/formatting: ruff + black (backend), eslint + prettier (frontend)
- [ ] T006 [P] Create Dockerfile for backend in `service-docintel/Dockerfile`
- [ ] T007 [P] Create Dockerfile for frontend in `frontend/Dockerfile`
- [ ] T008 [P] Create docker-compose.yml at repo root for local development
- [ ] T009 [P] Create `.env.example` files for both services with all required keys

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [ ] T010 Create Pydantic settings config in `service-docintel/app/config.py`
- [ ] T011 Create PostgreSQL connection pool and base models in `service-docintel/app/services/storage/postgres.py`
- [ ] T012 Create Qdrant client and collection setup in `service-docintel/app/services/storage/qdrant.py`
- [ ] T013 Create Langfuse client and trace/span helpers in `service-docintel/app/services/observability/langfuse.py`
- [ ] T014 Create database initialization script in `service-docintel/app/db/init_db.py`
- [ ] T015 Create base Pydantic models for all entities in `service-docintel/app/models/` (document.py, chunk.py, agent.py, admin.py, dashboard.py)
- [ ] T016 Create FastAPI app with health check in `service-docintel/app/main.py`
- [ ] T017 Create API route modules structure in `service-docintel/app/api/` (documents.py, chat.py, dashboard.py, admin.py)
- [ ] T018 [P] Create TypeScript types for frontend in `frontend/types/index.ts`
- [ ] T019 [P] Setup Tailwind CSS with color palette in `frontend/tailwind.config.ts`
- [ ] T020 [P] Create API client utility in `frontend/lib/api.ts`
- [ ] T021 [P] Create auth context/hook for seed user in `frontend/lib/auth.tsx`

**Checkpoint**: Foundation ready - user story implementation can now begin in parallel

---

## Phase 3: User Story 1 - PDF Document Ingestion (Priority: P1) 🎯 MVP

**Goal**: Users can upload PDF documents, process them through intelligent parsing pipeline (page-type routing to LlamaParse/pdfplumber/pypdf), chunk by page, embed with text-embedding-3-small, and store in PostgreSQL + Qdrant

**Independent Test**: Upload a multi-page PDF with mixed content types, verify all pages parse correctly, chunks created with correct metadata, vectors stored in Qdrant, document metadata in PostgreSQL

### Implementation for User Story 1

- [ ] T022 [P] [US1] Create parser routing logic in `service-docintel/app/services/ingestion/parser.py` (LlamaParse for image/chart/scanned, pdfplumber for tables, pypdf for text)
- [ ] T023 [P] [US1] Create page chunker in `service-docintel/app/services/ingestion/chunker.py` (configurable chunk size/overlap from admin config)
- [ ] T024 [P] [US1] Create embedder in `service-docintel/app/services/ingestion/embedder.py` (text-embedding-3-small via OpenAI)
- [ ] T025 [US1] Create ingestion pipeline orchestrator in `service-docintel/app/services/ingestion/pipeline.py` (coordinates parser → chunker → embedder → storage)
- [ ] T026 [US1] Implement document upload endpoint in `service-docintel/app/api/documents.py` (POST /documents/upload, 50MB limit, duplicate filename check)
- [ ] T027 [US1] Implement document list endpoint in `service-docintel/app/api/documents.py` (GET /documents with status filter)
- [ ] T028 [US1] Implement document process endpoint in `service-docintel/app/api/documents.py` (POST /documents/{file_id}/process)
- [ ] T029 [US1] Implement document delete endpoint in `service-docintel/app/api/documents.py` (DELETE /documents/{file_id} - removes from PG and Qdrant)
- [ ] T030 [US1] Implement document chunks endpoint in `service-docintel/app/api/documents.py` (GET /documents/{file_id}/chunks)
- [ ] T031 [US1] Add status tracking (pending → processing → completed/failed) with error_message field
- [ ] T032 [P] [US1] Create Knowledge page UI in `frontend/app/knowledge/page.tsx` (upload, list, process, delete)
- [ ] T033 [P] [US1] Create upload component with drag-drop in `frontend/components/UploadZone.tsx`
- [ ] T034 [P] [US1] Create document list/table component in `frontend/components/DocumentTable.tsx`
- [ ] T035 [US1] Connect Knowledge page to backend API endpoints

**Checkpoint**: At this point, User Story 1 should be fully functional and testable independently - can upload, process, list, delete PDFs

---

## Phase 4: User Story 2 - Document Agent Chat with Guardrails (Priority: P1) 🎯 MVP

**Goal**: Agent applies input validation guardrails (PII detection, prompt injection/jailbreak detection, NSFW detection, unsafe character cleaning, language detection) before classifying intent and routing to appropriate tasks

**Independent Test**: Send various test inputs through chat API, verify guardrails trigger correctly, intent classification works, appropriate task executes

### Implementation for User Story 2

- [ ] T036 [P] [US2] Create PII detection guardrail in `service-docintel/app/services/agent/guardrails.py` (detect PII, return refusal)
- [ ] T037 [P] [US2] Create prompt injection/jailbreak detection in `service-docintel/app/services/agent/guardrails.py`
- [ ] T038 [P] [US2] Create NSFW content detection in `service-docintel/app/services/agent/guardrails.py`
- [ ] T039 [P] [US2] Create unsafe character cleaning in `service-docintel/app/services/agent/guardrails.py` (HTML tags like <trusted_content>, <safe_for_work>)
- [ ] T040 [P] [US2] Create language detection in `service-docintel/app/services/agent/guardrails.py`
- [ ] T041 [US2] Create guardrail orchestrator in `service-docintel/app/services/agent/guardrails.py` (runs all checks sequentially)
- [ ] T042 [P] [US2] Create intent classification in `service-docintel/app/services/agent/intent.py` (need_plan, social_question)
- [ ] T043 [P] [US2] Create task type definitions in `service-docintel/app/services/agent/tasks.py` (document_metadata, knowledge_retrieval, summary)
- [ ] T044 [US2] Implement document_metadata task in `service-docintel/app/services/agent/tasks.py` (total count + document names)
- [ ] T045 [US2] Implement summary task in `service-docintel/app/services/agent/tasks.py` (chat history summary, no retrieval)
- [ ] T046 [US2] Create main agent flow in `service-docintel/app/services/agent/flow.py` (guardrails → intent → task routing)
- [ ] T047 [US2] Add chat session management (create session, store messages) in `service-docintel/app/services/storage/postgres.py`
- [ ] T048 [US2] Implement chat endpoint with SSE streaming in `service-docintel/app/api/chat.py` (POST /chat with X-Request-Id header)
- [ ] T049 [US2] Implement chat sessions endpoints in `service-docintel/app/api/chat.py` (GET /chat/sessions, GET /chat/sessions/{session_id})
- [ ] T050 [P] [US2] Create Agent page UI in `frontend/app/agent/page.tsx` (chat interface, streaming, waiting buffer)
- [ ] T051 [P] [US2] Create chat message components in `frontend/components/ChatMessage.tsx` (user/assistant bubbles, markdown)
- [ ] T052 [P] [US2] Create streaming hook in `frontend/lib/useChatStream.ts` (SSE consumption, token buffering)
- [ ] T053 [P] [US2] Create citation rendering component in `frontend/components/Citation.tsx` (filename, page, clickable)
- [ ] T054 [US2] Connect Agent page to backend streaming chat API

**Checkpoint**: At this point, User Story 2 should be fully functional - guardrails work, intent classification routes correctly, chat streams responses

---

## Phase 5: User Story 3 - Knowledge Retrieval & Answer Generation (Priority: P1) 🎯 MVP

**Goal**: Hybrid retrieval (BM25 + vector RRF, top-k=5), evidence evaluation (sufficient/not_sufficient/not_relevant), structured generation with citations, post-generation review (correctness, grounded, clean_format, PII masking)

**Independent Test**: Ask factual questions against ingested documents, verify retrieval finds relevant chunks, answers contain proper citations, review guardrails pass

### Implementation for User Story 3

- [ ] T055 [P] [US3] Create BM25 search in `service-docintel/app/services/agent/retrieval.py` (PostgreSQL tsvector)
- [ ] T056 [P] [US3] Create vector search in `service-docintel/app/services/agent/retrieval.py` (Qdrant)
- [ ] T057 [US3] Create hybrid RRF fusion in `service-docintel/app/services/agent/retrieval.py` (combines BM25 + vector)
- [ ] T058 [US3] Create retrieval orchestrator in `service-docintel/app/services/agent/retrieval.py` (uses admin config for method/top_k)
- [ ] T059 [US3] Create evidence evaluation in `service-docintel/app/services/agent/evidence.py` (sufficient/not_sufficient/not_relevant with rephrase retry)
- [ ] T060 [P] [US3] Create structured output models for citations in `service-docintel/app/models/agent.py` (Citation, AgentResponse)
- [ ] T061 [US3] Create answer generator in `service-docintel/app/services/agent/generator.py` (OpenAI structured output with citations, streaming)
- [ ] T062 [US3] Create post-generation review in `service-docintel/app/services/agent/reviewer.py` (correctness, grounded, clean_format, contain_pii)
- [ ] T063 [US3] Integrate retrieval → evidence → generation → review into agent flow in `service-docintel/app/services/agent/flow.py`
- [ ] T064 [US3] Add Langfuse tracing to all agent steps in `service-docintel/app/services/agent/flow.py` (spans for each sub-process)
- [ ] T065 [US3] Add runtime logging to PostgreSQL for dashboard in `service-docintel/app/services/agent/flow.py`
- [ ] T066 [US3] Update chat endpoint to use full agent flow with all steps
- [ ] T067 [P] [US3] Update citation rendering in `frontend/components/Citation.tsx` (excerpt display, clickable to source)

**Checkpoint**: At this point, User Story 3 should be fully functional - retrieval finds evidence, answers cite sources, review passes

---

## Phase 6: User Story 4 - Knowledge Management Frontend (Priority: P2)

**Goal**: Complete web interface for document management - login, upload (<50MB), process, delete, list with status

**Independent Test**: Navigate to knowledge page, login, upload PDF, process, verify status updates, delete, verify removal

### Implementation for User Story 4

- [ ] T068 [P] [US4] Create Login page in `frontend/app/login/page.tsx` (admin/123456 seed credentials)
- [ ] T069 [P] [US4] Create auth middleware/protection for protected routes in `frontend/middleware.ts`
- [ ] T070 [P] [US4] Style Knowledge page with Tailwind (color palette: #91BBBB, #429393, #9C9D6E, #FFFFFF)
- [ ] T071 [US4] Add loading states and error handling to Knowledge page components
- [ ] T072 [US4] Add file size validation (<50MB) and PDF type check on frontend
- [ ] T073 [US4] Add status badge indicators (pending/processing/completed/failed) with colors
- [ ] T074 [US4] Add confirmation dialog for document deletion
- [ ] T075 [US4] Add toast notifications for upload/process/delete actions

**Checkpoint**: At this point, User Story 4 should be fully functional - polished knowledge management UI

---

## Phase 7: User Story 5 - Agent Chat Frontend (Priority: P2)

**Goal**: Polished chat interface with streaming responses, proper citation rendering, interactive waiting buffer like ChatGPT/Claude

**Independent Test**: Navigate to agent page, ask question, verify streaming response appears, citations render correctly, waiting buffer shows during generation

### Implementation for User Story 5

- [ ] T076 [P] [US5] Create interactive waiting buffer animation in `frontend/components/WaitingBuffer.tsx`
- [ ] T077 [P] [US5] Create streaming answer renderer in `frontend/components/StreamingAnswer.tsx` (progressive token display)
- [ ] T078 [US5] Implement citation click-through to document/chunk view in `frontend/components/Citation.tsx`
- [ ] T079 [US5] Add markdown rendering for agent responses in `frontend/components/ChatMessage.tsx`
- [ ] T080 [US5] Add chat history sidebar in `frontend/components/ChatSidebar.tsx` (session list, new chat)
- [ ] T081 [US5] Add auto-scroll to bottom during streaming
- [ ] T082 [US5] Add copy-to-clipboard for code blocks in responses
- [ ] T083 [US5] Add regeneration/retry for failed responses
- [ ] T084 [US5] Polish Agent page layout and responsiveness

**Checkpoint**: At this point, User Story 5 should be fully functional - polished chat UX matching ChatGPT/Claude

---

## Phase 8: User Story 6 - Dashboard & Admin Frontend (Priority: P3)

**Goal**: Dashboard with knowledge summary (total files, status) and agent activity (total questions, runtime stats: fastest/avg/longest), Admin page to configure chunk size, chunk overlap, retrieval method, top-k

**Independent Test**: Navigate to dashboard, verify stats display; navigate to admin, change settings, verify persistence and effect on subsequent operations

### Implementation for User Story 6

- [ ] T085 [P] [US6] Create Dashboard page in `frontend/app/dashboard/page.tsx`
- [ ] T086 [P] [US6] Create Admin page in `frontend/app/admin/page.tsx`
- [ ] T087 [P] [US6] Create dashboard stats cards in `frontend/components/StatsCard.tsx`
- [ ] T088 [P] [US6] Create runtime stats chart in `frontend/components/RuntimeChart.tsx`
- [ ] T089 [US6] Implement dashboard stats endpoint in `service-docintel/app/api/dashboard.py` (GET /dashboard/stats)
- [ ] T090 [US6] Implement admin config endpoints in `service-docintel/app/api/admin.py` (GET/PUT /admin/config)
- [ ] T091 [US6] Create admin config form in `frontend/components/AdminConfigForm.tsx` (chunk_size, chunk_overlap, retrieval_method, top_k)
- [ ] T092 [US6] Add validation for admin config values (chunk_size 1-10, overlap 0-5, top_k 1-50)
- [ ] T093 [US6] Connect admin config to ingestion pipeline and retrieval (read from DB at runtime)
- [ ] T094 [US6] Add real-time stats refresh on Dashboard page

**Checkpoint**: At this point, User Story 6 should be fully functional - dashboard shows metrics, admin config works

---

## Phase 9: Evaluation & Observability (Cross-Cutting)

**Purpose**: Evaluation runner against eval_dataset.jsonl, Langfuse integration verification

- [ ] T095 [P] Create evaluation runner in `service-docintel/evals/run_eval.py` (reads eval_dataset.jsonl, runs agent, compares results)
- [ ] T096 [P] Update eval_dataset.jsonl to align with current specification **(prerequisite for T095)**
- [ ] T097 [US3] Verify Langfuse traces appear correctly (one trace per chat, spans for guardrails/intent/retrieval/generation/review)
- [ ] T098 [US3] Add eval results storage to PostgreSQL (eval_runs table)
- [ ] T099 [US6] Display evaluation results on Dashboard or Admin page
+ [ ] T100 [P] [US3] Create retrieval quality metrics in `service-docintel/app/services/agent/retrieval_metrics.py` (precision@k, recall@k, MRR tracking for SC-003)
+ [ ] T101 [P] [US2] Create guardrail test suite in `service-docintel/tests/guardrails/` (PII, injection, NSFW test cases with expected pass/fail for SC-004)
+ [ ] T102 [P] [US2] Add guardrail validation to eval runner (run guardrail tests automatically, report block rate)

---

## Phase 10: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories

- [ ] T103 [P] Add comprehensive error handling and user-friendly error messages
- [ ] T104 [P] Add request logging middleware in `service-docintel/app/main.py`
- [ ] T105 [P] Add CORS configuration for frontend origin
- [ ] T106 [P] Create README.md with setup and deployment instructions
- [ ] T107 [P] Verify quickstart.md steps work end-to-end
- [ ] T108 [P] Add Vercel deployment configuration (vercel.json for backend)
- [ ] T109 [P] Add Vercel deployment configuration (vercel.json for frontend)
- [ ] T110 [P] Run full eval_dataset.jsonl and verify pass rate
- [ ] T111 [P] Performance test: 50-page PDF ingestion < 60s, chat response P95 < 10s
- [ ] T112 [P] Security review: validate all inputs, no SQL injection, proper auth checks
+ [ ] T113 [P] Frontend performance: bundle analysis, code splitting, lazy loading for <3s load (SC-007)
+ [ ] T114 [P] Concurrent upload stress test: 5 simultaneous 50MB PDFs (SC-010)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Story 1 (Phase 3)**: Depends on Foundational (Phase 2)
- **User Story 2 (Phase 4)**: Depends on Foundational (Phase 2) + US1 (for document storage)
- **User Story 3 (Phase 5)**: Depends on Foundational (Phase 2) + US1 (for chunks) + US2 (agent flow)
- **User Story 4 (Phase 6)**: Depends on Foundational (Phase 2) + US1 (API endpoints)
- **User Story 5 (Phase 7)**: Depends on Foundational (Phase 2) + US2 (chat API) + US3 (full agent)
- **User Story 6 (Phase 8)**: Depends on Foundational (Phase 2) + US1/US3 (data for stats)
- **Evaluation (Phase 9)**: Depends on US1+US2+US3 complete
- **Polish (Phase 10)**: Depends on all desired user stories being complete

### User Story Dependencies

- **US1 (P1)**: Can start after Foundational - No dependencies on other stories
- **US2 (P1)**: Can start after Foundational - Needs US1 for document storage, but guardrails/intent can be built independently
- **US3 (P1)**: Can start after Foundational - Needs US1 (chunks in Qdrant/PG) and US2 (agent flow structure)
- **US4 (P2)**: Can start after Foundational + US1 (API endpoints ready)
- **US5 (P2)**: Can start after Foundational + US2 (chat API) + US3 (full agent with retrieval)
- **US6 (P3)**: Can start after Foundational + US1/US3 (data for dashboard stats)

### Within Each User Story

- Tests (if included) MUST be written and FAIL before implementation
- Models before services
- Services before endpoints
- Backend endpoints before frontend integration
- Core implementation before polish

### Parallel Opportunities

- All Setup tasks marked [P] can run in parallel
- All Foundational tasks marked [P] can run in parallel (within Phase 2)
- Once Foundational phase completes, US1, US2, US3 can start in parallel (different backend service modules)
- US4, US5, US6 frontend work can proceed in parallel once their backend APIs are ready
- All [P] tasks within a story can run in parallel
- Different user stories can be worked on in parallel by different team members

---

## Parallel Example: User Story 1 (Ingestion Pipeline)

```bash
# Launch all parser/chunker/embedder implementations together:
Task: "Create parser routing logic in service-docintel/app/services/ingestion/parser.py"
Task: "Create page chunker in service-docintel/app/services/ingestion/chunker.py"
Task: "Create embedder in service-docintel/app/services/ingestion/embedder.py"

# Launch API endpoints together (different route functions):
Task: "Implement document upload endpoint in service-docintel/app/api/documents.py"
Task: "Implement document list endpoint in service-docintel/app/api/documents.py"
Task: "Implement document delete endpoint in service-docintel/app/api/documents.py"

# Launch frontend components together:
Task: "Create Knowledge page UI in frontend/app/knowledge/page.tsx"
Task: "Create upload component in frontend/components/UploadZone.tsx"
Task: "Create document list component in frontend/components/DocumentTable.tsx"
```

---

## Parallel Example: User Story 3 (Retrieval & Generation)

```bash
# Launch retrieval components together:
Task: "Create BM25 search in service-docintel/app/services/agent/retrieval.py"
Task: "Create vector search in service-docintel/app/services/agent/retrieval.py"
Task: "Create structured output models in service-docintel/app/models/agent.py"

# Launch generator/reviewer together:
Task: "Create answer generator in service-docintel/app/services/agent/generator.py"
Task: "Create post-generation review in service-docintel/app/services/agent/reviewer.py"
```

---

## Implementation Strategy

### MVP First (User Stories 1-3 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL - blocks all stories)
3. Complete Phase 3: User Story 1 (Ingestion)
4. Complete Phase 4: User Story 2 (Guardrails + Basic Agent)
5. Complete Phase 5: User Story 3 (Retrieval + Generation + Review)
6. **STOP and VALIDATE**: Test US1→US2→US3 flow independently
7. Deploy/demo if ready

### Incremental Delivery

1. Complete Setup + Foundational → Foundation ready
2. Add User Story 1 → Test independently → Deploy/Demo (ingestion works!)
3. Add User Story 2 → Test independently → Deploy/Demo (chat with guardrails!)
4. Add User Story 3 → Test independently → Deploy/Demo (full RAG works!)
5. Add User Story 4 → Test independently → Deploy/Demo (polished knowledge UI!)
6. Add User Story 5 → Test independently → Deploy/Demo (polished chat UI!)
7. Add User Story 6 → Test independently → Deploy/Demo (dashboard + admin!)
8. Each story adds value without breaking previous stories

### Parallel Team Strategy

With multiple developers:

1. Team completes Setup + Foundational together
2. Once Foundational is done:
   - Developer A: User Story 1 (ingestion pipeline + knowledge page)
   - Developer B: User Story 2 (guardrails + intent + agent flow + chat page)
   - Developer C: User Story 3 (retrieval + generation + review)
3. Once US1-3 backend done:
   - Developer A: User Story 4 (knowledge page polish)
   - Developer B: User Story 5 (chat page polish)
   - Developer C: User Story 6 (dashboard + admin)
4. Stories complete and integrate independently

---

## Summary

- **Total Tasks**: 114
- **Tasks per User Story**: US1: 14, US2: 22, US3: 16, US4: 8, US5: 9, US6: 9, Foundational: 12, Setup: 9, Polish: 12, Eval: 5
- **Parallel Opportunities**: 54 tasks marked [P] across all phases
- **Independent Test Criteria**: Each user story has defined independent test in spec.md
- **Suggested MVP Scope**: User Stories 1-3 (Ingestion + Guardrails/Agent + Retrieval/Generation)
- **Format Validation**: ALL tasks follow checklist format with checkbox, Task ID, [P] where applicable, [Story] label for user story tasks, exact file paths