from pydantic import BaseModel, Field
from uuid import UUID
from datetime import datetime
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
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True