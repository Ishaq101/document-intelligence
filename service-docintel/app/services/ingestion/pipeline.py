"""Ingestion orchestration: parse, chunk, embed, store."""
import logging
import os
from dataclasses import dataclass
from typing import Optional
from uuid import UUID

from app.services.ingestion.chunker import Chunk, chunk_document
from app.services.ingestion.embedder import Embedder, get_embedder
from app.services.ingestion.parser import parse_document
from app.services.storage.postgres import insert_chunks, update_document_status
from app.services.storage.qdrant import QdrantManager

logger = logging.getLogger(__name__)


@dataclass
class IngestionResult:
    file_id: str
    page_count: int
    chunk_count: int
    status: str


class IngestionPipeline:
    """Coordinate document ingestion without retaining file or DB connections."""

    def __init__(
        self,
        chunk_size_kb: int = 2,
        chunk_overlap_kb: int = 0,
        embedder: Optional[Embedder] = None,
    ):
        self.chunk_size_kb = chunk_size_kb
        self.chunk_overlap_kb = chunk_overlap_kb
        self.embedder = embedder

    async def _get_embedder(self) -> Embedder:
        return self.embedder or await get_embedder()

    async def ingest_document(
        self,
        file_path: str,
        file_id: UUID,
        user_id: UUID,
        filename: Optional[str] = None,
        category: Optional[str] = None,
    ) -> IngestionResult:
        """Ingest one PDF and return its persisted evidence summary."""
        try:
            pages = await parse_document(file_path)
            if not pages:
                raise ValueError("No content extracted from document")

            page_count = len(pages)
            await update_document_status(file_id, "processing", page_count, user_id=user_id)
            chunks: list[Chunk] = chunk_document(
                pages,
                filename or os.path.basename(file_path),
                str(file_id),
                self.chunk_size_kb,
                self.chunk_overlap_kb,
            )
            if not chunks:
                raise ValueError("No chunks created from document")

            for chunk in chunks:
                chunk.category = category or chunk.category
            embedded_chunks = await (await self._get_embedder()).embed_chunks(chunks)
            await insert_chunks(embedded_chunks)
            await QdrantManager.upsert_chunks(embedded_chunks, category)
            await update_document_status(file_id, "completed", page_count, user_id=user_id)
            return IngestionResult(str(file_id), page_count, len(chunks), "completed")
        except Exception as error:
            logger.exception("Ingestion failed for %s", file_id)
            await update_document_status(file_id, "failed", error_message=str(error), user_id=user_id)
            raise


async def ingest_document(
    file_path: str,
    file_id: UUID,
    user_id: UUID,
    filename: Optional[str] = None,
    category: Optional[str] = None,
    chunk_size_kb: int = 2,
    chunk_overlap_kb: int = 0,
) -> IngestionResult:
    """Run ingestion with default service configuration."""
    return await IngestionPipeline(chunk_size_kb, chunk_overlap_kb).ingest_document(
        file_path, file_id, user_id, filename, category
    )