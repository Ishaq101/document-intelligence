import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import admin, chat, dashboard, documents
from app.config import settings
from app.services.llm_client import close_openai_client
from app.services.observability.langfuse import initialize_langfuse, shutdown_langfuse
from app.services.storage.postgres import PostgresPool, init_db
from app.services.storage.qdrant import QdrantManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    # Startup
    logger.info("Starting Document Intelligence API...")
    await init_db()
    await QdrantManager.initialize_collection()
    initialize_langfuse()
    logger.info("Application startup complete")

    yield

    # Shutdown
    logger.info("Shutting down Document Intelligence API...")
    await PostgresPool.close()
    await QdrantManager.close()
    # Close the model client before flushing telemetry so its last spans are still collected.
    await close_openai_client()
    shutdown_langfuse()
    logger.info("Application shutdown complete")


app = FastAPI(
    title="Document Intelligence API",
    description="Document Intelligence System with PDF ingestion, RAG, and agent chat",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "document-intelligence"}


# Import and include API routers
app.include_router(documents.router, prefix="/documents", tags=["documents"])
app.include_router(chat.router, prefix="/chat", tags=["chat"])
app.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
app.include_router(admin.router, prefix="/admin", tags=["admin"])
