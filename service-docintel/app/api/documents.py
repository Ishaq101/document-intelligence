import logging
import tempfile
from pathlib import Path
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, File, HTTPException, Query, Response, UploadFile

from app.models.document import (
    DocumentResponse,
    DocumentListResponse,
    DocumentStatus,
)
from app.models.chunk import ChunkResponse
from app.services.ingestion.pipeline import IngestionPipeline
from app.services.storage.object_storage import ObjectStorage
from app.services.storage.postgres import DOCUMENTS_TABLE, PostgresPool

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/upload", response_model=DocumentResponse, status_code=201)
async def upload_document(
    file: UploadFile = File(...),
    category: str = Query(..., min_length=1, max_length=100, description="Admin-defined document category"),
    user_id: UUID = UUID("00000000-0000-0000-0000-000000000001"),  # Seed user
):
    """Upload a PDF document for ingestion."""
    # Validate file type
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")

    # Read file content
    content = await file.read()
    if len(content) > 50_000_000:  # 50MB limit
        raise HTTPException(status_code=400, detail="File size exceeds 50MB limit")

    # Check for duplicate filename
    pool = await PostgresPool.get_pool()
    async with pool.acquire() as conn:
        existing = await conn.fetchrow(
            f"SELECT file_id FROM {DOCUMENTS_TABLE} WHERE filename = $1 AND user_id = $2",
            file.filename,
            user_id,
        )
        if existing:
            raise HTTPException(status_code=409, detail="Document with this filename already exists")

    from app.services.storage.postgres import category_exists, create_document

    if not await category_exists(category):
        raise HTTPException(status_code=422, detail="Category must be created by an admin first")

    # Create record only after source object has been persisted.
    document = await create_document(
        filename=file.filename,
        file_size_bytes=len(content),
        user_id=user_id,
        category=category,
    )
    try:
        await ObjectStorage.upload_pdf(document["file_id"], content)
    except Exception as error:
        from app.services.storage.postgres import delete_document as delete_document_record

        await delete_document_record(document["file_id"], user_id)
        logger.exception("Could not store source PDF %s", document["file_id"])
        raise HTTPException(status_code=502, detail="Could not store source PDF") from error

    return DocumentResponse(
        file_id=document["file_id"],
        filename=document["filename"],
        file_size_bytes=document["file_size_bytes"],
        user_id=document["user_id"],
        status=document["status"],
        page_count=document["page_count"],
        category=document["category"],
        upload_timestamp=document["upload_timestamp"],
        processed_timestamp=document["processed_timestamp"],
        error_message=document["error_message"],
    )


@router.get("", response_model=DocumentListResponse)
async def list_documents(
    status: Optional[DocumentStatus] = Query(None),
    user_id: UUID = UUID("00000000-0000-0000-0000-000000000001"),  # Seed user
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """List documents with optional status filter"""
    from app.services.storage.postgres import list_documents as list_docs

    documents, total = await list_docs(
        user_id=user_id,
        status=status,
        limit=limit,
        offset=offset,
    )

    return DocumentListResponse(
        documents=[DocumentResponse(**doc) for doc in documents],
        total=total,
    )


@router.post("/{file_id}/process", response_model=DocumentResponse)
async def ingest_uploaded_document(
    file_id: UUID,
    user_id: UUID = UUID("00000000-0000-0000-0000-000000000001"),  # Seed user
):
    """Process a document through the ingestion pipeline"""
    from app.services.storage.postgres import get_admin_config, get_document, update_document_status

    document = await get_document(file_id, user_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    if document["status"] == DocumentStatus.PROCESSING:
        raise HTTPException(status_code=409, detail="Document is already being ingested")
    if document["status"] == DocumentStatus.COMPLETED:
        raise HTTPException(status_code=409, detail="Document has already been ingested")

    # Update status to processing
    await update_document_status(file_id, DocumentStatus.PROCESSING, user_id=user_id)

    # Download source only for this ingestion. File disappears after request completion.
    with tempfile.TemporaryDirectory(prefix="docintel-") as temp_dir:
        file_path = Path(temp_dir) / f"{file_id}.pdf"
        if not await ObjectStorage.download_pdf(file_id, file_path):
            await update_document_status(
                file_id,
                DocumentStatus.FAILED,
                error_message="Source file not found",
                user_id=user_id,
            )
            raise HTTPException(status_code=404, detail="Source file not found for ingestion")

        try:
            config = await get_admin_config()
            pipeline = IngestionPipeline(
                chunk_size_kb=config["chunk_size"],
                chunk_overlap_kb=config["chunk_overlap"],
            )
            result = await pipeline.ingest_document(
                str(file_path),
                file_id,
                user_id,
                document["filename"],
                document["category"],
            )
            await update_document_status(
                file_id,
                DocumentStatus.COMPLETED,
                page_count=result.page_count,
                user_id=user_id,
            )
        except Exception as error:
            logger.exception("Ingestion failed for %s", file_id)
            await update_document_status(
                file_id,
                DocumentStatus.FAILED,
                error_message=str(error),
                user_id=user_id,
            )
            raise HTTPException(status_code=500, detail="Document ingestion failed") from error

    # Return updated document
    updated = await get_document(file_id, user_id)
    return DocumentResponse(**updated)


@router.delete("/{file_id}", status_code=204)
async def delete_document(
    file_id: UUID,
    user_id: UUID = UUID("00000000-0000-0000-0000-000000000001"),  # Seed user
):
    """Delete a document and its chunks from PostgreSQL and Qdrant"""
    from app.services.storage.postgres import delete_document
    from app.services.storage.qdrant import QdrantManager

    deleted = await delete_document(file_id, user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Document not found")

    # Delete vector and source-object copies.
    await QdrantManager.delete_document_chunks(file_id)
    await ObjectStorage.delete_pdf(file_id)

    return Response(status_code=204)


@router.get("/{file_id}/chunks", response_model=list[ChunkResponse])
async def get_document_chunks(
    file_id: UUID,
    user_id: UUID = UUID("00000000-0000-0000-0000-000000000001"),  # Seed user
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """Get chunks for a specific document"""
    from app.services.storage.postgres import get_document_chunks

    # Verify document exists and belongs to user
    from app.services.storage.postgres import get_document
    document = await get_document(file_id, user_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    chunks = await get_document_chunks(file_id, limit=limit, offset=offset)
    return [ChunkResponse(**chunk) for chunk in chunks]