# Data Model: Document Intelligence System

**Feature**: Document Intelligence System  
**Date**: 2025-01-15

---

## PostgreSQL Schema (Neon)

### `documents` table
Stores uploaded PDF metadata and processing status.

```sql
CREATE TABLE documents (
    file_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    filename VARCHAR(255) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    page_count INTEGER NOT NULL DEFAULT 0,
    file_size_bytes BIGINT NOT NULL,
    upload_timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    processed_timestamp TIMESTAMP WITH TIME ZONE,
    error_message TEXT,
    CONSTRAINT valid_status CHECK (status IN ('pending', 'processing', 'completed', 'failed')),
    CONSTRAINT unique_user_filename UNIQUE (user_id, filename)
);

CREATE INDEX idx_documents_user_id ON documents(user_id);
CREATE INDEX idx_documents_status ON documents(status);
CREATE INDEX idx_documents_filename ON documents(filename);
```

### `chunks` table
Stores page-level chunks with metadata for filtering and retrieval.

```sql
CREATE TABLE chunks (
    chunk_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    file_id UUID NOT NULL REFERENCES documents(file_id) ON DELETE CASCADE,
    filename VARCHAR(255) NOT NULL,
    page INTEGER NOT NULL,
    category VARCHAR(100),
    company VARCHAR(100),
    content TEXT NOT NULL,
    -- vector_content stored in Qdrant, not here
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_chunks_file_id ON chunks(file_id);
CREATE INDEX idx_chunks_filename ON chunks(filename);
CREATE INDEX idx_chunks_page ON chunks(page);
CREATE INDEX idx_chunks_category ON chunks(category);
CREATE INDEX idx_chunks_company ON chunks(company);
-- Full-text search index for BM25
CREATE INDEX idx_chunks_content_fts ON chunks USING GIN (to_tsvector('english', content));
```

### `chat_sessions` table
Tracks conversation sessions for observability and history.

```sql
CREATE TABLE chat_sessions (
    session_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    trace_id VARCHAR(100),  -- Langfuse trace ID
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_chat_sessions_user_id ON chat_sessions(user_id);
CREATE INDEX idx_chat_sessions_trace_id ON chat_sessions(trace_id);
```

### `messages` table
Stores individual messages with citations and runtime metrics.

```sql
CREATE TABLE messages (
    message_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES chat_sessions(session_id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL,  -- 'user' | 'assistant'
    content TEXT NOT NULL,
    citations JSONB,  -- Array of {filename, page, chunk_id, excerpt}
    runtime_ms INTEGER,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    CONSTRAINT valid_role CHECK (role IN ('user', 'assistant'))
);

CREATE INDEX idx_messages_session_id ON messages(session_id);
CREATE INDEX idx_messages_timestamp ON messages(timestamp);
```

### `admin_config` table
Single-row table for runtime configuration (admin page).

```sql
CREATE TABLE admin_config (
    id INTEGER PRIMARY KEY DEFAULT 1,
    chunk_size INTEGER NOT NULL DEFAULT 1,
    chunk_overlap INTEGER NOT NULL DEFAULT 0,
    retrieval_method VARCHAR(20) NOT NULL DEFAULT 'hybrid_rrf',
    top_k INTEGER NOT NULL DEFAULT 5,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    CONSTRAINT single_row CHECK (id = 1),
    CONSTRAINT valid_retrieval_method CHECK (retrieval_method IN ('bm25', 'vector', 'hybrid_rrf'))
);

INSERT INTO admin_config (id) VALUES (1) ON CONFLICT DO NOTHING;
```

### `eval_runs` table
Stores evaluation results for tracking quality over time.

```sql
CREATE TABLE eval_runs (
    run_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    test_case_id VARCHAR(50) NOT NULL,
    category VARCHAR(50) NOT NULL,
    question TEXT NOT NULL,
    predicted_answer TEXT,
    expected_answer TEXT,
    passed BOOLEAN NOT NULL,
    runtime_ms INTEGER,
    citations JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_eval_runs_test_case ON eval_runs(test_case_id);
CREATE INDEX idx_eval_runs_created_at ON eval_runs(created_at);
```

---

## Qdrant Collection Schema

### Collection: `document_chunks`

```python
# Vector configuration
vector_params = VectorParams(
    size=1536,  # text-embedding-3-small dimension
    distance=Distance.COSINE
)

# Payload indexes for filtering (matching PostgreSQL filterable fields)
payload_indexes = [
    PayloadSchemaType.KEYWORD,  # filename
    PayloadSchemaType.KEYWORD,  # file_id
    PayloadSchemaType.INTEGER,  # page
    PayloadSchemaType.KEYWORD,  # category
    PayloadSchemaType.KEYWORD,  # company
]

# Point structure
{
    "id": "<chunk_id_uuid>",
    "vector": [float, ...],  # 1536 dimensions
    "payload": {
        "filename": "Kirana_Logistics_Annual_Report_2025.pdf",
        "file_id": "uuid-string",
        "page": 1,
        "category": "financial",
        "company": "Kirana Logistics",
        "content": "Page text content..."
    }
}
```

---

## Pydantic Models (Backend)

### Document Models (`models/document.py`)

```python
from pydantic import BaseModel, Field
from uuid import UUID
from datetime import datetime
from typing import Optional, List
from enum import Enum

class DocumentStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

class DocumentBase(BaseModel):
    filename: str = Field(..., max_length=255)
    file_size_bytes: int = Field(..., gt=0, le=50_000_000)

class DocumentCreate(DocumentBase):
    pass

class DocumentResponse(DocumentBase):
    file_id: UUID
    user_id: UUID
    status: DocumentStatus
    page_count: int
    upload_timestamp: datetime
    processed_timestamp: Optional[datetime] = None
    error_message: Optional[str] = None

    class Config:
        from_attributes = True

class DocumentListResponse(BaseModel):
    documents: List[DocumentResponse]
    total: int
```

### Chunk Models (`models/chunk.py`)

```python
from pydantic import BaseModel, Field
from uuid import UUID
from typing import Optional

class ChunkBase(BaseModel):
    filename: str
    file_id: UUID
    page: int = Field(..., ge=1)
    category: Optional[str] = None
    company: Optional[str] = None
    content: str

class ChunkCreate(ChunkBase):
    pass

class ChunkResponse(ChunkBase):
    chunk_id: UUID
    created_at: datetime

    class Config:
        from_attributes = True
```

### Agent Models (`models/agent.py`)

```python
from pydantic import BaseModel, Field
from typing import List, Optional, Literal
from uuid import UUID
from datetime import datetime
from enum import Enum

class IntentType(str, Enum):
    NEED_PLAN = "need_plan"
    SOCIAL_QUESTION = "social_question"
    SINGLE_TASK = "single_task"

class TaskType(str, Enum):
    DOCUMENT_METADATA = "document_metadata"
    KNOWLEDGE_RETRIEVAL = "knowledge_retrieval"
    SUMMARY = "summary"

class EvidenceStatus(str, Enum):
    SUFFICIENT = "evidence_sufficient"
    NOT_SUFFICIENT = "evidence_not_sufficient"
    NOT_RELEVANT = "evidence_not_relevant"

class RetrievalMethod(str, Enum):
    BM25 = "bm25"
    VECTOR = "vector"
    HYBRID_RRF = "hybrid_rrf"

class Citation(BaseModel):
    filename: str
    page: int
    chunk_id: UUID
    excerpt: Optional[str] = None

class GuardrailResult(BaseModel):
    passed: bool
    reason: Optional[str] = None
    cleaned_input: Optional[str] = None

class IntentClassification(BaseModel):
    need_plan: bool
    social_question: bool
    task_types: List[TaskType] = []
    language: str = "en"

class RetrievalResult(BaseModel):
    chunks: List[ChunkResponse]
    evidence_status: EvidenceStatus
    rephrased_query: Optional[str] = None

class AgentResponse(BaseModel):
    answer: str
    citations: List[Citation] = []
    confidence: Literal["high", "medium", "low"] = "medium"
    evidence_sufficient: bool = True
    language: str = "en"

class ReviewResult(BaseModel):
    correctness: bool
    grounded: bool
    clean_format: bool
    contain_pii: bool
    repaired_answer: Optional[str] = None

class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=4000)
    session_id: Optional[UUID] = None

class ChatResponse(BaseModel):
    session_id: UUID
    answer: str
    citations: List[Citation] = []
    runtime_ms: int
```

### Admin Models (`models/admin.py`)

```python
from pydantic import BaseModel, Field
from typing import Optional

class AdminConfigResponse(BaseModel):
    chunk_size: int = Field(..., ge=1, le=10)
    chunk_overlap: int = Field(..., ge=0, le=5)
    retrieval_method: RetrievalMethod
    top_k: int = Field(..., ge=1, le=50)

class AdminConfigUpdate(BaseModel):
    chunk_size: Optional[int] = Field(None, ge=1, le=10)
    chunk_overlap: Optional[int] = Field(None, ge=0, le=5)
    retrieval_method: Optional[RetrievalMethod] = None
    top_k: Optional[int] = Field(None, ge=1, le=50)
```

### Dashboard Models (`models/dashboard.py`)

```python
from pydantic import BaseModel
from typing import List

class DashboardStats(BaseModel):
    total_files: int
    status_counts: dict  # {"pending": 2, "completed": 10, "failed": 1}
    total_questions: int
    runtime_stats: RuntimeStats

class RuntimeStats(BaseModel):
    fastest_ms: int
    average_ms: float
    longest_ms: int
```

---

## Frontend TypeScript Types (`frontend/types/index.ts`)

```typescript
export type DocumentStatus = 'pending' | 'processing' | 'completed' | 'failed';

export interface Document {
  file_id: string;
  user_id: string;  // UUID string
  filename: string;
  status: DocumentStatus;
  page_count: number;
  file_size_bytes: number;
  upload_timestamp: string;
  processed_timestamp?: string;
  error_message?: string;
}

export interface Chunk {
  chunk_id: string;
  file_id: string;
  filename: string;
  page: number;
  category?: string;
  company?: string;
  content: string;
}

export interface Citation {
  filename: string;
  page: number;
  chunk_id: string;
  excerpt?: string;
}

export interface ChatMessage {
  message_id: string;
  session_id: string;
  role: 'user' | 'assistant';
  content: string;
  citations?: Citation[];
  runtime_ms?: number;
  timestamp: string;
}

export interface ChatSession {
  session_id: string;
  user_id: string;  // UUID string
  trace_id?: string;
  created_at: string;
  updated_at: string;
}

export interface AdminConfig {
  chunk_size: number;
  chunk_overlap: number;
  retrieval_method: 'bm25' | 'vector' | 'hybrid_rrf';
  top_k: number;
}

export interface DashboardStats {
  total_files: number;
  status_counts: Record<DocumentStatus, number>;
  total_questions: number;
  runtime_stats: {
    fastest_ms: number;
    average_ms: number;
    longest_ms: number;
  };
}
```

---

## Entity Relationship Diagram

```
documents (1) ──────< (N) chunks
    │
    │ (file_id cascade delete)
    ▼
chat_sessions (1) ──────< (N) messages
    │
    │ (session_id)
    ▼
eval_runs (independent, references test_case_id)

admin_config (single row, no relations)
```

---

## Filterable/Retrievable Fields (per spec)

| Field | PostgreSQL Index | Qdrant Payload Index | Use Case |
|-------|------------------|---------------------|----------|
| filename | BTREE + UNIQUE (per user) | KEYWORD | Filter by document |
| file_id | BTREE (FK) | KEYWORD | Join with documents |
| page | BTREE | INTEGER | Page-level citation |
| category | BTREE | KEYWORD | Domain filtering |
| company | BTREE | KEYWORD | Multi-tenant ready |
| content | GIN (tsvector) | — | BM25 search |
| vector_content | — | HNSW (vector) | Semantic search |