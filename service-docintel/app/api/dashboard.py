import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Query
from app.models.dashboard import DashboardResponse, EvalRunResponse
from app.services.storage.postgres import (
    CHUNKS_TABLE,
    CHAT_SESSIONS_TABLE,
    DOCUMENTS_TABLE,
    MESSAGES_TABLE,
    PostgresPool,
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/stats", response_model=DashboardResponse)
async def get_dashboard_stats(
    user_id: UUID = UUID("00000000-0000-0000-0000-000000000001"),  # Seed user
):
    """Get dashboard statistics for knowledge and agent activity"""
    pool = await PostgresPool.get_pool()
    async with pool.acquire() as conn:
        # Knowledge stats
        knowledge = await conn.fetchrow(
            f"""
            SELECT
                COUNT(*) as total_files,
                COUNT(*) FILTER (WHERE status = 'pending') as files_pending,
                COUNT(*) FILTER (WHERE status = 'processing') as files_processing,
                COUNT(*) FILTER (WHERE status = 'completed') as files_completed,
                COUNT(*) FILTER (WHERE status = 'failed') as files_failed
            FROM {DOCUMENTS_TABLE}
            WHERE user_id = $1
            """,
            user_id,
        )

        total_chunks = await conn.fetchval(
            f"""
            SELECT COUNT(*) FROM {CHUNKS_TABLE} c
            JOIN {DOCUMENTS_TABLE} d ON c.file_id = d.file_id
            WHERE d.user_id = $1
            """,
            user_id,
        )

        agent = await conn.fetchrow(
            f"""
            SELECT
                COUNT(*) FILTER (WHERE role = 'user') as total_questions,
                MIN(runtime_ms) FILTER (WHERE role = 'assistant' AND runtime_ms IS NOT NULL) as fastest_runtime_ms,
                AVG(runtime_ms) FILTER (WHERE role = 'assistant' AND runtime_ms IS NOT NULL) as average_runtime_ms,
                MAX(runtime_ms) FILTER (WHERE role = 'assistant' AND runtime_ms IS NOT NULL) as longest_runtime_ms
            FROM {MESSAGES_TABLE} m
            JOIN {CHAT_SESSIONS_TABLE} cs ON m.session_id = cs.session_id
            WHERE cs.user_id = $1
            """,
            user_id,
        )

        return DashboardResponse(
            knowledge={
                "total_files": knowledge["total_files"] or 0,
                "files_pending": knowledge["files_pending"] or 0,
                "files_processing": knowledge["files_processing"] or 0,
                "files_completed": knowledge["files_completed"] or 0,
                "files_failed": knowledge["files_failed"] or 0,
                "total_chunks": total_chunks or 0,
            },
            agent={
                "total_questions": agent["total_questions"] or 0,
                "fastest_runtime_ms": agent["fastest_runtime_ms"],
                "average_runtime_ms": float(agent["average_runtime_ms"]) if agent["average_runtime_ms"] else None,
                "longest_runtime_ms": agent["longest_runtime_ms"],
            }
        )


@router.get("/eval-runs", response_model=list[EvalRunResponse])
async def list_eval_runs(
    user_id: UUID = UUID("00000000-0000-0000-0000-000000000001"),  # Seed user
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """List evaluation runs"""
    pool = await PostgresPool.get_pool()
    async with pool.acquire() as conn:
        runs = await conn.fetch("""
            SELECT run_id, dataset_name, total_cases, passed, failed, avg_score, created_at
            FROM eval_runs
            WHERE user_id = $1
            ORDER BY created_at DESC
            LIMIT $2 OFFSET $3
        """, user_id, limit, offset)

        return [EvalRunResponse(**dict(run)) for run in runs]