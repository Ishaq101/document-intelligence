from pydantic import BaseModel, Field
from uuid import UUID
from typing import Literal, Optional
from enum import Enum

from app.models.chunk import ChunkResponse


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
    task_types: list[TaskType] = Field(default_factory=list)
    language: str = "en"


class RetrievalResult(BaseModel):
    chunks: list[ChunkResponse]
    evidence_status: EvidenceStatus
    rephrased_query: Optional[str] = None


class AgentResponse(BaseModel):
    answer: str
    citations: list[Citation] = Field(default_factory=list)
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
    citations: list[Citation] = Field(default_factory=list)
    runtime_ms: int