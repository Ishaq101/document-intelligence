# Feature Specification: Document Intelligence System

**Feature Branch**: `001-document-intelligence`

**Created**: 2025-01-15

**Status**: Draft

**Input**: User description: "Create comprehensive specification for document intelligence system with PDF ingestion pipeline, document agent with guardrails, retrieval, generation, and frontend"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - PDF Document Ingestion (Priority: P1)

Users can upload PDF documents to the system, which are processed through an intelligent parsing pipeline that routes each page to the appropriate parser based on content type (images/charts → LlamaParse, tables → pdfplumber, scanned → LlamaParse, text-only → pypdf), then chunked by page, embedded, and stored in both PostgreSQL (metadata) and Qdrant (vectors).

**Why this priority**: Core foundation - without ingestion, no documents exist to query.

**Independent Test**: Upload a multi-page PDF with mixed content types, verify all pages parse correctly, chunks created with correct metadata, vectors stored in Qdrant, document metadata in PostgreSQL.

**Acceptance Scenarios**:

1. **Given** a PDF with mixed content (text pages, tables, charts, images), **When** user uploads and processes it, **Then** each page routes to correct parser and ingestion completes successfully.
2. **Given** a scanned PDF, **When** user uploads it, **Then** LlamaParse extracts text via OCR and ingestion succeeds.
3. **Given** a PDF with duplicate filename, **When** user attempts upload, **Then** system rejects with clear error.
4. **Given** an existing document, **When** user deletes it, **Then** both PostgreSQL metadata and Qdrant vectors are removed.

---

### User Story 2 - Document Agent Chat with Guardrails (Priority: P1)

Users can chat with the document agent which applies input validation guardrails (PII detection, prompt injection/jailbreak detection, NSFW content detection, unsafe character cleaning, language detection) before classifying intent and routing to appropriate tasks.

**Why this priority**: Core interaction - users need safe, intelligent conversation with their documents.

**Independent Test**: Send various test inputs through chat API, verify guardrails trigger correctly, intent classification works, appropriate task executes.

**Acceptance Scenarios**:

1. **Given** user sends message with PII, **When** agent processes it, **Then** graceful refusal returned without processing PII.
2. **Given** user sends prompt injection attempt, **When** agent processes it, **Then** graceful refusal returned.
3. **Given** user sends NSFW content, **When** agent processes it, **Then** graceful refusal returned.
4. **Given** user sends message with unsafe HTML tags, **When** agent processes it, **Then** tags cleaned and processing continues.
5. **Given** user sends message in Indonesian, **When** agent responds, **Then** response is in Indonesian.
6. **Given** user says "hello", **When** agent processes it, **Then** social_question intent detected, direct answer without retrieval.
7. **Given** user asks complex multi-part question, **When** agent processes it, **Then** need_plan=true, multiple tasks execute in order.

---

### User Story 3 - Knowledge Retrieval & Answer Generation (Priority: P1)

Agent retrieves relevant evidence from knowledge base using hybrid search (BM25 + vector with RRF, top-k=5), evaluates evidence sufficiency, generates structured answers with citations, and applies post-generation review (correctness, groundedness, format, PII masking).

**Why this priority**: Core value - accurate, cited answers from user's documents.

**Independent Test**: Ask factual questions against ingested documents, verify retrieval finds relevant chunks, answers contain proper citations, review guardrails pass.

**Acceptance Scenarios**:

1. **Given** user asks factual question with answer in documents, **When** agent processes, **Then** hybrid retrieval finds evidence, answer generated with citations.
2. **Given** user asks question where evidence is insufficient, **When** agent processes, **Then** evidence_not_sufficient detected, honest response about limitation.
3. **Given** user asks question with no relevant evidence, **When** agent processes, **Then** evidence_not_relevant detected, query rephrased and re-tried, then honest refusal if still no evidence.
4. **Given** answer generated, **When** review runs, **Then** correctness, grounded, clean_format, contain_pii all verified.
5. **Given** streaming response, **When** frontend receives, **Then** tokens stream progressively like ChatGPT/Claude.

---

### User Story 4 - Knowledge Management Frontend (Priority: P2)

Users can access a web interface to login (admin/123456), view document list with status, upload PDFs (<50MB), trigger ingestion processing, and delete documents.

**Why this priority**: Primary user interface for document management.

**Independent Test**: Navigate to knowledge page, login, upload PDF, process, verify status updates, delete, verify removal.

**Acceptance Scenarios**:

1. **Given** user visits login page, **When** enters admin/123456, **Then** authenticated and redirected to knowledge page.
2. **Given** user on knowledge page, **When** uploads PDF <50MB, **Then** file appears in list with "pending" status.
3. **Given** document in list, **When** user clicks process, **Then** ingestion runs, status updates to "completed" or "failed".
4. **Given** processed document, **When** user clicks delete, **Then** document removed from list and backend storage.

---

### User Story 5 - Agent Chat Frontend (Priority: P2)

Users can chat with document agent through web interface with streaming responses, proper citation rendering, and interactive waiting buffer.

**Why this priority**: Primary user interface for querying documents.

**Independent Test**: Navigate to agent page, ask question, verify streaming response appears, citations render correctly.

**Acceptance Scenarios**:

1. **Given** user on agent page, **When** sends question, **Then** interactive waiting buffer shows while awaiting response.
2. **Given** agent streaming response, **When** frontend receives tokens, **Then** response renders progressively.
3. **Given** response contains citations, **When** rendered, **Then** citations display with filename and page, clickable to source.

---

### User Story 6 - Dashboard & Admin Frontend (Priority: P3)

Users can view dashboard with knowledge summary (total files, status) and agent activity (total questions, runtime stats: fastest/avg/longest), and admins can configure chunk size, chunk overlap, retrieval method, top-k.

**Why this priority**: Observability and configuration for system tuning.

**Independent Test**: Navigate to dashboard, verify stats display; navigate to admin, change settings, verify persistence.

**Acceptance Scenarios**:

1. **Given** user on dashboard, **When** page loads, **Then** total files, status counts, total questions, runtime stats displayed.
2. **Given** user on admin page, **When** changes chunk size/overlap/retrieval method/top-k, **Then** settings persist and affect subsequent ingestion/queries.

---

### Edge Cases

- What happens when PDF exceeds 50MB? → Reject with clear error message
- What happens when ingestion fails mid-pipeline? → Document status shows "failed" with error details, partial cleanup
- What happens when Qdrant/PostgreSQL unavailable? → Graceful degradation with user-facing error, logged for debugging
- What happens when Langfuse unavailable? → Logging continues locally, observability degraded but core function works
- What happens when user asks question in language not in documents? → Agent responds in user's language, notes if evidence language differs
- What happens when multiple users upload simultaneously? → Each upload handled independently, filename conflicts detected per-session

---

## Requirements *(mandatory)*

### Functional Requirements

#### Ingestion Pipeline

- **FR-001**: System MUST accept PDF file uploads up to 50MB
- **FR-002**: System MUST reject uploads with duplicate filenames (within same upload batch or existing documents)
- **FR-003**: System MUST route each PDF page to appropriate parser based on content type: images/charts/scanned → LlamaParse, tables → pdfplumber, text-only → pypdf
- **FR-004**: System MUST chunk documents by page (configurable chunk size default 1, overlap default 0)
- **FR-005**: System MUST embed chunks using text-embedding-3-small model
- **FR-006**: System MUST store chunk metadata in PostgreSQL: filename, file_id, chunk_id, page, category, company, content
- **FR-007**: System MUST store vector embeddings in Qdrant with vector_content field
- **FR-008**: System MUST delete both PostgreSQL metadata and Qdrant vectors when document deleted
- **FR-009**: System MUST track document status: pending, processing, completed, failed

#### Document Agent - Guardrails

- **FR-010**: System MUST detect PII in user input and refuse gracefully without processing
- **FR-011**: System MUST detect prompt injection/jailbreak attempts and refuse gracefully
- **FR-012**: System MUST detect NSFW content (crimes, pornography, human trafficking, religion issues) and refuse gracefully
- **FR-013**: System MUST detect and clean unsafe characters/formatting (HTML tags like <trusted_content>, <safe_for_work>) then continue processing
- **FR-014**: System MUST detect user language or requested language and respond in that language

#### Document Agent - Intent Classification

- **FR-015**: System MUST classify intent as need_plan=true for complex multi-task requests
- **FR-016**: System MUST classify intent as need_plan=false for single-task requests
- **FR-017**: System MUST classify social_question=true for chit-chat (hello, thank you, bye) and answer directly without retrieval

#### Document Agent - Tasks

- **FR-018**: System MUST support document_metadata task: return total document count and document names from knowledge base
- **FR-019**: System MUST support knowledge_retrieval task: find evidence/facts from knowledge base
- **FR-020**: System MUST support summary task: summarize chat history without retrieval

#### Document Agent - Retrieval

- **FR-021**: System MUST support BM25 keyword search only
- **FR-022**: System MUST support vector search only
- **FR-023**: System MUST support hybrid search with RRF (default)
- **FR-024**: System MUST use top-k=5 by default (configurable via admin)

#### Document Agent - Evidence Evaluation

- **FR-025**: System MUST evaluate evidence as sufficient → proceed to generation
- **FR-026**: System MUST evaluate evidence as not_sufficient → honest response about limitation
- **FR-027**: System MUST evaluate evidence as not_relevant → rephrase query and re-retrieve once, then honest refusal if still not relevant

#### Document Agent - Generation

- **FR-028**: System MUST use structured output with Pydantic for consistent responses
- **FR-029**: System MUST limit max output tokens to 4096
- **FR-030**: System MUST set thinking effort to medium for models supporting it
- **FR-031**: System MUST stream responses to frontend
- **FR-032**: System MUST include citations (filename, page, chunk_id) for evidence-based answers via structured output

#### Document Agent - Post-Generation Review

- **FR-033**: System MUST verify correctness (answer proper and correct)
- **FR-034**: System MUST verify grounded (answer uses internal knowledge, not hallucinated)
- **FR-035**: System MUST verify clean_format (no broken markdown/formatting)
- **FR-036**: System MUST verify no PII in output (mask until clean)

#### Observability & Logging

- **FR-037**: System MUST log environment setup, critical process errors, critical debugging info as first priority
- **FR-038**: System MUST use Langfuse free tier for LLM observability: one trace per chat, spans for sub-processes
- **FR-039**: System MUST log runtime duration in database for dashboard display

#### Evaluation

- **FR-040**: System MUST support running evaluation against eval_dataset.jsonl using sample document (Kirana Logistics Annual Report 2025)

#### Frontend - Login

- **FR-041**: System MUST provide login page with seed credentials admin/123456

#### Frontend - Knowledge Management

- **FR-042**: System MUST display document list with status
- **FR-043**: System MUST support PDF upload (<50MB)
- **FR-044**: System MUST support triggering ingestion processing
- **FR-045**: System MUST support document deletion (removes from UI and backend)

#### Frontend - Agent Chat

- **FR-046**: System MUST provide chat interface with text input
- **FR-047**: System MUST render streaming responses progressively
- **FR-048**: System MUST show interactive waiting buffer during response generation
- **FR-049**: System MUST render citations properly (filename, page, clickable)
- **FR-050**: System MUST support markdown/HTML output rendering

#### Frontend - Dashboard

- **FR-051**: System MUST display total files and status summary
- **FR-052**: System MUST display total questions asked
- **FR-053**: System MUST display runtime stats: fastest, average, longest response time

#### Frontend - Admin

- **FR-054**: System MUST allow configuring chunk size
- **FR-055**: System MUST allow configuring chunk overlap
- **FR-056**: System MUST allow configuring retrieval method (BM25, vector, hybrid RRF)
- **FR-057**: System MUST allow configuring top-k

#### Deployment

- **FR-058**: System MUST provide Dockerfile for backend service
- **FR-059**: System MUST provide Dockerfile for frontend
- **FR-060**: System MUST support separate deployment to Vercel

---

### Key Entities

- **Document**: Represents an uploaded PDF file with attributes: file_id, filename, status, page_count, upload_timestamp, file_size
- **Chunk**: Represents a page-level segment of a document with attributes: chunk_id, file_id, filename, page, category, company, content, vector_content
- **ChatSession**: Represents a conversation with attributes: session_id, user_id, messages, trace_id (Langfuse), created_at
- **Message**: Represents a single chat message with attributes: message_id, session_id, role (user/assistant), content, citations, runtime_ms, timestamp
- **EvalTestCase**: Represents an evaluation test case with attributes: test_case_id, category, question, expected_result (retrieve_chunks, expected_citations, expected_answer, expected_entities, should_abstain)

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can upload and process a 50-page PDF with mixed content types in under 60 seconds
- **SC-002**: Agent responds to factual questions with relevant citations in under 10 seconds (P95)
- **SC-003**: Hybrid retrieval (RRF) returns relevant evidence for 90% of eval dataset factual questions
- **SC-004**: Guardrails correctly block 100% of PII, injection, NSFW test cases in eval dataset
- **SC-005**: Streaming responses begin rendering within 2 seconds of request
- **SC-006**: Document deletion removes all associated data from both PostgreSQL and Qdrant within 5 seconds
- **SC-007**: Frontend loads and becomes interactive within 3 seconds on first visit
- **SC-008**: Admin configuration changes take effect immediately for subsequent operations
- **SC-009**: Evaluation runner completes full eval_dataset.jsonl in under 5 minutes
- **SC-010**: System handles concurrent uploads of 5 documents without errors

---

## Assumptions

- Users have stable internet connectivity for frontend access
- LLM API (GPT-6 Luna) and embedding API (text-embedding-3-small) are available and within quota
- Neon PostgreSQL free tier provides sufficient storage for document metadata
- Qdrant Cloud free tier provides sufficient vector storage
- Langfuse free tier provides sufficient observability capacity
- Seed user admin/123456 is acceptable for demo purposes (no production auth needed)
- PDF-only support is sufficient for MVP (no DOCX, images, etc.)
- Single-user demo deployment (no multi-tenancy, no RBAC)
- Evaluation dataset aligns with current specification (may need updates per spec section 86)
- Frontend deployed separately on Vercel, backend on separate Vercel or container platform
- No caching mechanism needed for MVP (per spec section 75-76)
- Chunk size/overlap configuration applies to future ingestions, not retroactively
- Language detection covers major languages; fallback to English if undetected