# Remediation Edits for Top Analysis Issues

## Issue A3: Fix Duplicate Task ID T087

**File**: `specs/001-document-intelligence/tasks.md`

**Edit**: Renumber second T087 to T088 and shift subsequent tasks

```diff
- [ ] T087 [P] [US6] Create dashboard stats cards in `frontend/components/StatsCard.tsx`
- [ ] T087 [P] [US6] Create runtime stats chart in `frontend/components/RuntimeChart.tsx`
- [ ] T088 [US6] Implement dashboard stats endpoint in `service-docintel/app/api/dashboard.py` (GET /dashboard/stats)
- [ ] T089 [US6] Implement admin config endpoints in `service-docintel/app/api/admin.py` (GET/PUT /admin/config)
- [ ] T090 [US6] Create admin config form in `frontend/components/AdminConfigForm.tsx` (chunk_size, chunk_overlap, retrieval_method, top_k)
- [ ] T091 [US6] Add validation for admin config values (chunk_size 1-10, overlap 0-5, top_k 1-50)
- [ ] T092 [US6] Connect admin config to ingestion pipeline and retrieval (read from DB at runtime)
- [ ] T093 [US6] Add real-time stats refresh on Dashboard page
```

```diff
+ [ ] T087 [P] [US6] Create dashboard stats cards in `frontend/components/StatsCard.tsx`
+ [ ] T088 [P] [US6] Create runtime stats chart in `frontend/components/RuntimeChart.tsx`
+ [ ] T089 [US6] Implement dashboard stats endpoint in `service-docintel/app/api/dashboard.py` (GET /dashboard/stats)
+ [ ] T090 [US6] Implement admin config endpoints in `service-docintel/app/api/admin.py` (GET/PUT /admin/config)
+ [ ] T091 [US6] Create admin config form in `frontend/components/AdminConfigForm.tsx` (chunk_size, chunk_overlap, retrieval_method, top_k)
+ [ ] T092 [US6] Add validation for admin config values (chunk_size 1-10, overlap 0-5, top_k 1-50)
+ [ ] T093 [US6] Connect admin config to ingestion pipeline and retrieval (read from DB at runtime)
+ [ ] T094 [US6] Add real-time stats refresh on Dashboard page
```

**Note**: Also update Phase 9 task IDs (T094→T095, T095→T096, T096→T097, T097→T098, T098→T099) and Phase 10 (T099→T100, etc.)

---

## Issue A4/A5: Add Retrieval Quality & Guardrail Validation Tasks

**File**: `specs/001-document-intelligence/tasks.md`

**Edit**: Add tasks in Phase 9 (Evaluation & Observability)

```diff
## Phase 9: Evaluation & Observability (Cross-Cutting)

**Purpose**: Evaluation runner against eval_dataset.jsonl, Langfuse integration verification

- [ ] T094 [P] Create evaluation runner in `service-docintel/evals/run_eval.py` (reads eval_dataset.jsonl, runs agent, compares results)
- [ ] T095 [P] Update eval_dataset.jsonl to align with current specification
- [ ] T096 [US3] Verify Langfuse traces appear correctly (one trace per chat, spans for guardrails/intent/retrieval/generation/review)
- [ ] T097 [US3] Add eval results storage to PostgreSQL (eval_runs table)
- [ ] T098 [US6] Display evaluation results on Dashboard or Admin page
```

```diff
## Phase 9: Evaluation & Observability (Cross-Cutting)

**Purpose**: Evaluation runner against eval_dataset.jsonl, Langfuse integration verification

- [ ] T094 [P] Create evaluation runner in `service-docintel/evals/run_eval.py` (reads eval_dataset.jsonl, runs agent, compares results)
- [ ] T095 [P] Update eval_dataset.jsonl to align with current specification
- [ ] T096 [US3] Verify Langfuse traces appear correctly (one trace per chat, spans for guardrails/intent/retrieval/generation/review)
- [ ] T097 [US3] Add eval results storage to PostgreSQL (eval_runs table)
- [ ] T098 [US6] Display evaluation results on Dashboard or Admin page
+ [ ] T099 [P] [US3] Create retrieval quality metrics in `service-docintel/app/services/agent/retrieval_metrics.py` (precision@k, recall@k, MRR tracking for SC-003)
+ [ ] T100 [P] [US2] Create guardrail test suite in `service-docintel/tests/guardrails/` (PII, injection, NSFW test cases with expected pass/fail for SC-004)
+ [ ] T101 [P] [US2] Add guardrail validation to eval runner (run guardrail tests automatically, report block rate)
```

---

## Issue A6/A7: Add Frontend Performance & Concurrent Upload Tasks

**File**: `specs/001-document-intelligence/tasks.md`

**Edit**: Add tasks in Phase 10 (Polish & Cross-Cutting Concerns)

```diff
## Phase 10: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories

- [ ] T099 [P] Add comprehensive error handling and user-friendly error messages
- [ ] T100 [P] Add request logging middleware in `service-docintel/app/main.py`
- [ ] T101 [P] Add CORS configuration for frontend origin
- [ ] T102 [P] Create README.md with setup and deployment instructions
- [ ] T103 [P] Verify quickstart.md steps work end-to-end
- [ ] T104 [P] Add Vercel deployment configuration (vercel.json for both services)
- [ ] T105 [P] Run full eval_dataset.jsonl and verify pass rate
- [ ] T106 [P] Performance test: 50-page PDF ingestion < 60s, chat response P95 < 10s
- [ ] T107 [P] Security review: validate all inputs, no SQL injection, proper auth checks
```

```diff
## Phase 10: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories

- [ ] T102 [P] Add comprehensive error handling and user-friendly error messages
- [ ] T103 [P] Add request logging middleware in `service-docintel/app/main.py`
- [ ] T104 [P] Add CORS configuration for frontend origin
- [ ] T105 [P] Create README.md with setup and deployment instructions
- [ ] T106 [P] Verify quickstart.md steps work end-to-end
- [ ] T107 [P] Add Vercel deployment configuration (vercel.json for backend)
- [ ] T108 [P] Add Vercel deployment configuration (vercel.json for frontend)
- [ ] T109 [P] Run full eval_dataset.jsonl and verify pass rate
- [ ] T110 [P] Performance test: 50-page PDF ingestion < 60s, chat response P95 < 10s
- [ ] T111 [P] Security review: validate all inputs, no SQL injection, proper auth checks
+ [ ] T112 [P] Frontend performance: bundle analysis, code splitting, lazy loading for <3s load (SC-007)
+ [ ] T113 [P] Concurrent upload stress test: 5 simultaneous 50MB PDFs (SC-010)
```

---

## Issue A9/A10: Document Detection Methods in Research

**File**: `specs/001-document-intelligence/research.md`

**Edit**: Add detection method decisions after existing sections

```diff
## 6. Admin Config Persistence

### Decision: PostgreSQL table `admin_config` with single row

...
```

```diff
## 6. Admin Config Persistence

### Decision: PostgreSQL table `admin_config` with single row

...

---

## 7. Guardrail Detection Methods

### PII Detection
**Decision**: Use `presidio-analyzer` (Microsoft Presidio) for entity recognition
- Supports: PERSON, EMAIL, PHONE_NUMBER, LOCATION, NRP, CREDIT_CARD, etc.
- Configurable entity types and confidence thresholds
- Fallback: regex patterns for common formats (email, phone, ID numbers)

### Prompt Injection/Jailbreak Detection
**Decision**: Hybrid approach
- Pattern-based: Detect known injection patterns (ignore instructions, system prompt override, etc.)
- LLM-based: Use small classifier model (or GPT-4o-mini) to score injection probability
- Threshold: >0.8 confidence → block

### NSFW Content Detection
**Decision**: Use `transformers` with `unitary/toxic-bert` or `martin-ha/toxic-comment-model`
- Labels: toxic, severe_toxic, obscene, threat, insult, identity_hate
- Threshold: >0.7 on any label → block
- Custom keywords for domain-specific NSFW (crimes, trafficking, religion)

### Language Detection
**Decision**: Use `fasttext` language identification model (`lid.176.bin`)
- Supports 176 languages
- Fast (<1ms), offline, no API calls
- Fallback: `langdetect` library if fasttext unavailable
- Confidence threshold: >0.9, else default to English

### Unsafe Character Cleaning
**Decision**: HTML sanitization with `bleach` library
- Strip: `<trusted_content>`, `<safe_for_work>`, `<system>`, `<user>`, `<assistant>`, script/style tags
- Allow: basic markdown formatting tags (b, i, code, pre, a, ul, ol, li)
- Preserve: Unicode text, emojis
```

---

## Issue A11: Define Review Prompt Templates in Research

**File**: `specs/001-document-intelligence/research.md`

**Edit**: Add after Guardrail Detection Methods section

```diff
### Unsafe Character Cleaning
**Decision**: HTML sanitization with `bleach` library
- Strip: `<trusted_content>`, `<safe_for_work>`, `<system>`, `<user>`, `<assistant>`, script/style tags
- Allow: basic markdown formatting tags (b, i, code, pre, a, ul, ol, li)
- Preserve: Unicode text, emojis
```

```diff
### Unsafe Character Cleaning
**Decision**: HTML sanitization with `bleach` library
- Strip: `<trusted_content>`, `<safe_for_work>`, `<system>`, `<user>`, `<assistant>`, script/style tags
- Allow: basic markdown formatting tags (b, i, code, pre, a, ul, ol, li)
- Preserve: Unicode text, emojis

---

## 8. Post-Generation Review Prompt Templates

### Correctness Review
**Prompt Template**:
```
You are a fact-checker. Compare the ANSWER against the EVIDENCE.
EVIDENCE:
{evidence_chunks}

ANSWER:
{answer}

Rate correctness: 
- "high" = all claims supported by evidence
- "medium" = minor unsupported claims or minor inaccuracies
- "low" = major hallucinations or contradicted by evidence

Return JSON: {"correctness": "high|medium|low", "issues": ["specific issue 1", ...]}
```

### Groundedness Review
**Prompt Template**:
```
You are a groundedness evaluator. Does the ANSWER use ONLY information from the EVIDENCE?
EVIDENCE:
{evidence_chunks}

ANSWER:
{answer}

Check for:
1. Claims not in evidence (hallucination)
2. External knowledge inserted
3. Speculation beyond evidence

Return JSON: {"grounded": true|false, "ungrounded_claims": ["claim 1", ...]}
```

### Clean Format Review
**Prompt Template**:
```
Check the ANSWER for formatting issues:
- Broken markdown (unclosed code fences, broken tables, bad links)
- Incomplete sentences
- Inconsistent citation format
- Mixed languages unexpectedly

Return JSON: {"clean_format": true|false, "issues": ["issue 1", ...]}
```

### PII Masking Review
**Prompt Template**:
```
Scan the ANSWER for PII:
- Names, emails, phones, addresses, IDs, financial info
- Any personal identifiers

If found, return masked version with [REDACTED] placeholders.
Return JSON: {"contain_pii": true|false, "masked_answer": "..."}
```
```

---

## Issue A12/A15: Align Entity Definitions in Spec

**File**: `specs/001-document-intelligence/spec.md`

**Edit**: Update Key Entities section to include user_id on Document

```diff
### Key Entities

- **Document**: Represents an uploaded PDF file with attributes: file_id, filename, status, page_count, upload_timestamp, file_size
- **Chunk**: Represents a page-level segment of a document with attributes: chunk_id, file_id, filename, page, category, company, content, vector_content
- **ChatSession**: Represents a conversation with attributes: session_id, user_id, messages, trace_id (Langfuse), created_at
- **Message**: Represents a single chat message with attributes: message_id, session_id, role (user/assistant), content, citations, runtime_ms, timestamp
- **EvalTestCase**: Represents an evaluation test case with attributes: test_case_id, category, question, expected_result (retrieve_chunks, expected_citations, expected_answer, expected_entities, should_abstain)
```

```diff
### Key Entities

- **Document**: Represents an uploaded PDF file with attributes: file_id, user_id, filename, status, page_count, upload_timestamp, file_size
- **Chunk**: Represents a page-level segment of a document with attributes: chunk_id, file_id, filename, page, category, company, content, vector_content
- **ChatSession**: Represents a conversation with attributes: session_id, user_id, messages, trace_id (Langfuse), created_at
- **Message**: Represents a single chat message with attributes: message_id, session_id, role (user/assistant), content, citations, runtime_ms, timestamp
- **EvalTestCase**: Represents an evaluation test case with attributes: test_case_id, category, question, expected_result (retrieve_chunks, expected_citations, expected_answer, expected_entities, should_abstain)
```

---

## Issue A13: Split Vercel Deployment Tasks

**File**: `specs/001-document-intelligence/tasks.md`

**Edit**: In Phase 10, split T104 into separate backend/frontend tasks (already shown in A6/A7 edit above)

---

## Summary of All Required Edits

| File | Edits Needed |
|------|--------------|
| `tasks.md` | Fix T087 duplicate, add 3 retrieval/guardrail tasks, add 2 frontend perf tasks, split Vercel task, renumber Phase 9-10 |
| `research.md` | Add Section 7 (Guardrail Detection Methods), Section 8 (Review Prompt Templates) |
| `spec.md` | Add `user_id` to Document entity in Key Entities |

**Total**: ~50 lines added across 3 files

**Want me to apply these edits?**