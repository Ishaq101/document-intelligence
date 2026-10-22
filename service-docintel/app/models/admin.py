from pydantic import BaseModel, Field
from typing import Literal, Optional


class AdminConfigBase(BaseModel):
    chunk_size: int = Field(..., ge=1, le=10, description="Chunk size in thousands of characters")
    chunk_overlap: int = Field(..., ge=0, le=5, description="Chunk overlap in thousands of characters")
    retrieval_method: Literal["bm25", "vector", "hybrid_rrf"] = "hybrid_rrf"
    top_k: int = Field(..., ge=1, le=50, description="Number of chunks to retrieve")


class AdminConfigCreate(AdminConfigBase):
    pass


class AdminConfigUpdate(BaseModel):
    chunk_size: Optional[int] = Field(None, ge=1, le=10)
    chunk_overlap: Optional[int] = Field(None, ge=0, le=5)
    retrieval_method: Optional[Literal["bm25", "vector", "hybrid_rrf"]] = None
    top_k: Optional[int] = Field(None, ge=1, le=50)


class AdminConfigResponse(AdminConfigBase):
    class Config:
        from_attributes = True


class CategoryCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, pattern=r"^\S(?:.*\S)?$")
    description: str = Field(..., min_length=1, max_length=1000, pattern=r"^\S(?:.*\S)?$")


class CategoryResponse(BaseModel):
    category_id: int
    name: str
    description: str


class DocumentCleanupResponse(BaseModel):
    deleted_documents: int
    deleted_vectors: int
    failed_source_deletions: int