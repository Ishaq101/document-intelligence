# Research Findings: Document Intelligence System

**Feature**: Document Intelligence System  
**Date**: 2025-01-15

---

## 1. LlamaParse Integration Pattern

### Decision: Async page-by-page with sync fallback

**Rationale**: LlamaParse Python SDK supports both sync and async. For page-by-page routing, we need to inspect page content type first. Since content detection requires parsing, we'll use LlamaParse's `get_json_result()` which returns structured data per page.

### Implementation Pattern

```python
# services/ingestion/parser.py
from llama_parse import LlamaParse
from pdfplumber import open as pdfplumber_open
from pypdf import PdfReader
import asyncio

class PageParser:
    def __init__(self, llama_api_key: str):
        self.llama = LlamaParse(api_key=llama_api_key, result_type="markdown")
    
    async def parse_page(self, pdf_path: str, page_num: int) -> ParsedPage:
        # First, detect page content type using pdfplumber
        page_type = await self._detect_page_type(pdf_path, page_num)
        
        if page_type in ("image", "chart", "scanned"):
            return await self._parse_with_llama(pdf_path, page_num)
        elif page_type == "table":
            return await self._parse_with_pdfplumber(pdf_path, page_num)
        else:  # text
            return await self._parse_with_pypdf(pdf_path, page_num)
    
    async def _detect_page_type(self, pdf_path: str, page_num: int) -> str:
        # Use pdfplumber to analyze page content
        with pdfplumber_open(pdf_path) as pdf:
            page = pdf.pages[page_num - 1]
            if page.images or page.chars_count < 50:  # heuristic
                return "scanned" if page.chars_count < 50 else "image"
            if page.extract_tables():
                return "table"
            # Check for charts via image analysis
            return "text"
```

**Quota Handling**: Catch `RateLimitError` from LlamaParse, log warning, continue with next parser (removed PaddleOCR per spec simplification).

---

## 2. Hybrid BM25 + Vector RRF Implementation

### Decision: PostgreSQL tsvector + Qdrant vector search with RRF in Python

**Rationale**: PostgreSQL has built-in full-text search (tsvector/tsquery). Qdrant provides vector search. RRF (Reciprocal Rank Fusion) combines ranked lists without score normalization.

### Implementation Pattern

```python
# services/agent/retrieval.py
from typing import List
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue
import asyncpg

class HybridRetriever:
    def __init__(self, pg_pool: asyncpg.Pool, qdrant: QdrantClient, collection: str):
        self.pg = pg_pool
        self.qdrant = qdrant
        self.collection = collection
    
    async def retrieve(self, query: str, top_k: int = 5, 
                       filter_conditions: dict = None) -> List[Chunk]:
        # BM25 from PostgreSQL
        bm25_results = await self._bm25_search(query, top_k * 2, filter_conditions)
        
        # Vector search from Qdrant
        vector_results = await self._vector_search(query, top_k * 2, filter_conditions)
        
        # RRF fusion
        return self._rrf_fuse(bm25_results, vector_results, top_k)
    
    async def _bm25_search(self, query: str, k: int, filters: dict) -> List[dict]:
        # Build tsquery from query terms
        tsquery = " & ".join(query.split())
        where_clause = self._build_where(filters)
        sql = f"""
            SELECT chunk_id, filename, file_id, page, category, company, content,
                   ts_rank_cd(to_tsvector('english', content), plainto_tsquery($1)) as rank
            FROM chunks
            {where_clause}
            ORDER BY rank DESC
            LIMIT $2
        """
        rows = await self.pg.fetch(sql, tsquery, k)
        return [dict(r) | {"source": "bm25", "rank": i} for i, r in enumerate(rows)]
    
    async def _vector_search(self, query: str, k: int, filters: dict) -> List[dict]:
        # Embed query first
        query_vector = await embed_text(query)
        qdrant_filter = self._build_qdrant_filter(filters)
        results = self.qdrant.search(
            collection_name=self.collection,
            query_vector=query_vector,
            query_filter=qdrant_filter,
            limit=k,
            with_payload=True
        )
        return [{"chunk_id": r.id, **r.payload, "score": r.score, "source": "vector", "rank": i} 
                for i, r in enumerate(results)]
    
    def _rrf_fuse(self, bm25: List[dict], vector: List[dict], k: int, rrf_k: int = 60) -> List[Chunk]:
        """Reciprocal Rank Fusion: score = 1/(k + rank)"""
        scores = {}
        for results in (bm25, vector):
            for item in results:
                cid = item["chunk_id"]
                scores[cid] = scores.get(cid, 0) + 1.0 / (rrf_k + item["rank"] + 1)
        
        # Sort by fused score, take top k, hydrate full chunk
        top_ids = sorted(scores, key=scores.get, reverse=True)[:k]
        # Fetch full chunks from PostgreSQL
        return await self._hydrate_chunks(top_ids)
```

---

## 3. Structured Output with Citations (Pydantic)

### Decision: Pydantic models with OpenAI `response_format` parameter

**Rationale**: OpenAI supports `response_format={"type": "json_schema", "json_schema": ...}` for structured output. Pydantic models define the schema, ensuring citations always present.

### Implementation Pattern

```python
# models/agent.py
from pydantic import BaseModel, Field
from typing import List, Optional, Literal

class Citation(BaseModel):
    filename: str
    page: int
    chunk_id: str
    excerpt: Optional[str] = None  # optional snippet for UI

class AgentResponse(BaseModel):
    answer: str = Field(..., description="Main answer text in markdown")
    citations: List[Citation] = Field(default_factory=list)
    confidence: Literal["high", "medium", "low"] = "medium"
    evidence_sufficient: bool = True
    language: str = "en"

# In generator:
async def generate_answer(question: str, evidence: List[Chunk]) -> AgentResponse:
    prompt = build_prompt(question, evidence)
    response = await openai_client.beta.chat.completions.parse(
        model="gpt-6-luna",
        messages=[{"role": "user", "content": prompt}],
        response_format=AgentResponse,
        max_tokens=4096,
        reasoning_effort="medium"
    )
    return response.choices[0].message.parsed
```

---

## 4. Langfuse Trace/Span Pattern

### Decision: One trace per chat request, spans for each agent step

**Rationale**: Spec requires "one chat on trace id, use spans on the same trace id for sub process". Langfuse Python SDK supports nested spans.

### Implementation Pattern

```python
# services/observability/langfuse.py
from langfuse import Langfuse
from contextvars import ContextVar

langfuse = Langfuse(
    public_key=settings.LANGFUSE_PUBLIC_KEY,
    secret_key=settings.LANGFUSE_SECRET_KEY,
    host=settings.LANGFUSE_BASE_URL
)

# Context var to propagate trace across async calls
current_trace: ContextVar[Optional["Trace"]] = ContextVar("current_trace", default=None)

def start_chat_trace(session_id: str, user_id: str, question: str) -> "Trace":
    trace = langfuse.trace(
        id=session_id,  # use session_id as trace_id
        name="chat_request",
        user_id=user_id,
        input={"question": question},
        metadata={"session_id": session_id}
    )
    current_trace.set(trace)
    return trace

def start_span(name: str, input_data: dict = None) -> "Span":
    trace = current_trace.get()
    if trace:
        return trace.span(name=name, input=input_data)
    return None

def end_span(span: "Span", output: dict = None, error: Exception = None):
    if span:
        span.end(output=output, error=error)

# Usage in agent flow:
async def agent_flow(question: str, session_id: str):
    trace = start_chat_trace(session_id, "admin", question)
    
    with start_span("guardrails", {"question": question}) as span:
        guardrails_result = await run_guardrails(question)
        end_span(span, {"result": guardrails_result})
    
    with start_span("intent_classification", {"question": question}) as span:
        intent = await classify_intent(question)
        end_span(span, {"intent": intent})
    
    # ... continue for retrieval, generation, review
    
    trace.update(output={"answer": final_answer})
    langfuse.flush()
```

---

## 5. FastAPI Streaming Response (SSE)

### Decision: Server-Sent Events with token-by-token streaming

**Rationale**: SSE is simpler than WebSockets, works natively with EventSource in browsers, supports automatic reconnection. Token streaming matches ChatGPT/Claude UX.

### Implementation Pattern

```python
# api/chat.py
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
import json

router = APIRouter()

@router.post("/chat")
async def chat_endpoint(request: Request, body: ChatRequest):
    async def event_generator():
        # Send initial event
        yield f"data: {json.dumps({'type': 'start', 'session_id': session_id})}\n\n"
        
        # Stream tokens from agent
        async for token in agent_stream_answer(body.question, session_id):
            yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"
        
        # Send citations at end
        yield f"data: {json.dumps({'type': 'citations', 'citations': citations})}\n\n"
        yield f"data: {json.dumps({'type': 'done', 'runtime_ms': runtime})}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # Disable nginx buffering
        }
    )
```

**Frontend consumption** (NextJS):
```typescript
// lib/chat.ts
export async function* streamChat(question: string) {
  const response = await fetch('/api/chat', {
    method: 'POST',
    body: JSON.stringify({ question }),
    headers: { 'Content-Type': 'application/json' }
  });
  
  const reader = response.body?.getReader();
  const decoder = new TextDecoder();
  
  while (true) {
    const { done, value } = await reader!.read();
    if (done) break;
    
    const chunk = decoder.decode(value);
    for (const line of chunk.split('\n')) {
      if (line.startsWith('data: ')) {
        yield JSON.parse(line.slice(6));
      }
    }
  }
}
```

---

## 6. Admin Config Persistence

### Decision: PostgreSQL table `admin_config` with single row

**Rationale**: Simple, survives restarts, accessible from both backend services. Admin page reads/writes this table. Defaults from spec (chunk_size=1, overlap=0, retrieval_method=hybrid_rrf, top_k=5).

### Schema

```sql
CREATE TABLE admin_config (
    id INTEGER PRIMARY KEY DEFAULT 1,
    chunk_size INTEGER NOT NULL DEFAULT 1,
    chunk_overlap INTEGER NOT NULL DEFAULT 0,
    retrieval_method VARCHAR(20) NOT NULL DEFAULT 'hybrid_rrf',
    top_k INTEGER NOT NULL DEFAULT 5,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    CONSTRAINT single_row CHECK (id = 1)
);

INSERT INTO admin_config (id) VALUES (1) ON CONFLICT DO NOTHING;
```

### API

```python
# api/admin.py
@router.get("/admin/config")
async def get_config():
    row = await pg.fetchrow("SELECT * FROM admin_config WHERE id = 1")
    return AdminConfig(**dict(row))

@router.put("/admin/config")
async def update_config(config: AdminConfigUpdate):
    await pg.execute("""
        UPDATE admin_config 
        SET chunk_size = COALESCE($1, chunk_size),
            chunk_overlap = COALESCE($2, chunk_overlap),
            retrieval_method = COALESCE($3, retrieval_method),
            top_k = COALESCE($4, top_k),
            updated_at = NOW()
        WHERE id = 1
    """, config.chunk_size, config.chunk_overlap, config.retrieval_method, config.top_k)
    return await get_config()
```

---

## Summary of Decisions

| Unknown | Decision | Key Technology |
|---------|----------|----------------|
| LlamaParse integration | Async page-by-page with content detection | llama-parse, pdfplumber, pypdf |
| Hybrid RRF | PostgreSQL tsvector + Qdrant + Python RRF | asyncpg, qdrant-client |
| Structured citations | Pydantic + OpenAI response_format | pydantic, openai beta |
| Langfuse tracing | Trace per chat, spans per step | langfuse Python SDK |
| Streaming | SSE token-by-token | FastAPI StreamingResponse |
| Admin config | PostgreSQL single-row table | asyncpg |

All unknowns resolved. Ready for Phase 1 design artifacts.

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