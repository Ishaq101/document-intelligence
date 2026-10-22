"""Direct agent tasks for metadata and conversation summaries."""
from typing import Optional, TypedDict
from uuid import UUID

from app.models.agent import TaskType
from app.services.storage.postgres import (
    CHUNKS_TABLE,
    DOCUMENTS_TABLE,
    PostgresPool,
    get_session_messages,
    list_documents,
)


class DocumentMetadata(TypedDict):
    file_id: str
    filename: str
    status: str
    page_count: int
    category: Optional[str]
    chunk_count: int


class DocumentMetadataResult(TypedDict):
    total: int
    documents: list[DocumentMetadata]
    message: str


class DocumentMetadataTask:
    """Read evidence registered by successful and pending document ingestion."""

    async def generate_answer(self, user_id: UUID) -> DocumentMetadataResult:
        documents, total = await list_documents(user_id, limit=1_000)
        if total == 0:
            return {"total": 0, "documents": [], "message": "You have no documents uploaded yet."}

        async with PostgresPool.acquire() as connection:
            rows = await connection.fetch(
                f"""
                SELECT d.file_id, COUNT(c.chunk_id) AS chunk_count
                FROM {DOCUMENTS_TABLE} d
                LEFT JOIN {CHUNKS_TABLE} c ON c.file_id = d.file_id
                WHERE d.user_id = $1
                GROUP BY d.file_id
                """,
                user_id,
            )
        chunk_counts = {str(row["file_id"]): int(row["chunk_count"]) for row in rows}
        evidence: list[DocumentMetadata] = [
            {
                "file_id": str(document["file_id"]),
                "filename": str(document["filename"]),
                "status": str(document["status"]),
                "page_count": int(document["page_count"]),
                "category": document["category"],
                "chunk_count": chunk_counts.get(str(document["file_id"]), 0),
            }
            for document in documents
        ]
        descriptions = [
            f"- {document['filename']} — Uploaded document ({document['status']})."
            for document in evidence[:5]
        ]
        return {
            "total": total,
            "documents": evidence,
            "message": "Available documents:\n" + "\n".join(descriptions),
        }


class SummaryTask:
    """Summarize chat history without document retrieval."""

    async def generate_answer(self, session_id: UUID, max_messages: int = 20) -> str:
        messages = await get_session_messages(session_id)
        if not messages:
            return "No conversation history to summarize."
        recent = messages[-max_messages:]
        conversation = "\n".join(
            f"{message['role'].capitalize()}: {message['content'][:200]}"
            for message in recent
        )
        return f"Conversation summary (last {len(recent)} messages):\n\n{conversation}"


async def execute_task(
    task_type: TaskType,
    user_id: UUID,
    session_id: Optional[UUID] = None,
) -> DocumentMetadataResult | str:
    """Execute non-retrieval task selected by intent classification."""
    if task_type == TaskType.DOCUMENT_METADATA:
        return await DocumentMetadataTask().generate_answer(user_id)
    if task_type == TaskType.SUMMARY and session_id:
        return await SummaryTask().generate_answer(session_id)
    raise ValueError(f"Unsupported direct task: {task_type}")