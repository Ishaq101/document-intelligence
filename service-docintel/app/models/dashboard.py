from pydantic import BaseModel, Field
from typing import Optional
from uuid import UUID
from datetime import datetime


class DashboardStats(BaseModel):
    total_files: int
    files_pending: int
    files_processing: int
    files_completed: int
    files_failed: int
    total_chunks: int


class AgentStats(BaseModel):
    total_questions: int
    fastest_runtime_ms: Optional[int] = None
    average_runtime_ms: Optional[float] = None
    longest_runtime_ms: Optional[int] = None


class DashboardResponse(BaseModel):
    knowledge: DashboardStats
    agent: AgentStats


class EvalRunBase(BaseModel):
    run_id: UUID
    dataset_name: str
    total_cases: int
    passed: int
    failed: int
    avg_score: Optional[float] = None
    created_at: datetime


class EvalRunResponse(EvalRunBase):
    class Config:
        from_attributes = True