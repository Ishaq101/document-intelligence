import logging
from uuid import UUID

from asyncpg import UniqueViolationError
from fastapi import APIRouter, HTTPException, status

from app.models.admin import (
    AdminConfigResponse,
    AdminConfigUpdate,
    CategoryCreate,
    CategoryResponse,
    DocumentCleanupResponse,
)
from app.services.storage.object_storage import ObjectStorage
from app.services.storage.postgres import (
    create_category,
    delete_all_documents,
    get_admin_config,
    list_categories,
    list_document_ids,
    update_admin_config as save_admin_config,
)
from app.services.storage.qdrant import QdrantManager

logger = logging.getLogger(__name__)
router = APIRouter()
ADMIN_USER_ID = UUID("00000000-0000-0000-0000-000000000001")


@router.get("/config", response_model=AdminConfigResponse)
async def get_config() -> AdminConfigResponse:
    """Get global configuration for this single-user demo."""
    return AdminConfigResponse(**await get_admin_config())


@router.put("/config", response_model=AdminConfigResponse)
async def update_config(config_update: AdminConfigUpdate) -> AdminConfigResponse:
    """Update global configuration."""
    current = await get_admin_config()
    chunk_size = config_update.chunk_size or current["chunk_size"]
    chunk_overlap = (
        config_update.chunk_overlap
        if config_update.chunk_overlap is not None
        else current["chunk_overlap"]
    )
    if chunk_overlap >= chunk_size:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="chunk_overlap must be smaller than chunk_size",
        )

    config = await save_admin_config(
        chunk_size=config_update.chunk_size,
        chunk_overlap=config_update.chunk_overlap,
        retrieval_method=config_update.retrieval_method,
        top_k=config_update.top_k,
    )
    return AdminConfigResponse(**config)


@router.get("/categories", response_model=list[CategoryResponse])
async def get_categories() -> list[CategoryResponse]:
    """List admin-defined document categories."""
    return [CategoryResponse(**category) for category in await list_categories()]


@router.post("/categories", response_model=CategoryResponse, status_code=status.HTTP_201_CREATED)
async def add_category(category: CategoryCreate) -> CategoryResponse:
    """Create a category available during document upload."""
    try:
        created = await create_category(category.name, category.description)
    except UniqueViolationError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Category already exists") from error
    return CategoryResponse(**created)


@router.delete("/documents", response_model=DocumentCleanupResponse)
async def cleanup_uploaded_documents() -> DocumentCleanupResponse:
    """Permanently remove all demo-user documents, vectors, and source PDFs."""
    document_ids = await list_document_ids(ADMIN_USER_ID)
    deleted_vectors = 0
    failed_source_deletions = 0

    for file_id in document_ids:
        deleted_vectors += await QdrantManager.count_document_chunks(file_id)
        await QdrantManager.delete_document_chunks(file_id)
        try:
            await ObjectStorage.delete_pdf(file_id)
        except Exception:
            failed_source_deletions += 1
            logger.exception("Could not remove source PDF for %s", file_id)

    deleted_documents = await delete_all_documents(ADMIN_USER_ID)
    return DocumentCleanupResponse(
        deleted_documents=deleted_documents,
        deleted_vectors=deleted_vectors,
        failed_source_deletions=failed_source_deletions,
    )