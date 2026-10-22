"""Embedder for document chunks using OpenAI text-embedding-3-small."""
import logging
from typing import List, Optional
import os

from app.services.ingestion.chunker import Chunk
from app.services.llm_client import get_openai_client

logger = logging.getLogger(__name__)


class Embedder:
    """Handles embedding generation for text chunks."""

    def __init__(self, api_key: Optional[str] = None, model: str = "text-embedding-3-small"):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model = model
        self._client = None

        if not self.api_key:
            logger.warning("OPENAI_API_KEY not set - embeddings will not work")

    @property
    def client(self):
        # Requests go through the shared client so sockets stay pooled; `api_key` only
        # signals whether credentials exist.
        if not self.api_key:
            return None
        if self._client is None:
            self._client = get_openai_client()
        return self._client

    async def embed_text(self, text: str) -> List[float]:
        """Generate embedding for a single text."""
        if not self.client:
            raise RuntimeError("OpenAI client not initialized - check OPENAI_API_KEY")

        try:
            response = await self.client.embeddings.create(
                model=self.model,
                input=text,
                encoding_format="float",
            )
            return response.data[0].embedding
        except Exception as e:
            logger.error(f"Embedding failed: {e}")
            raise

    async def embed_chunks(self, chunks: List[Chunk]) -> List[Chunk]:
        """Generate embeddings for multiple chunks."""
        if not self.client:
            raise RuntimeError("OpenAI client not initialized - check OPENAI_API_KEY")

        # Prepare texts
        texts = [chunk.content for chunk in chunks]

        try:
            # Batch embed (OpenAI supports batch)
            response = await self.client.embeddings.create(
                model=self.model,
                input=texts,
                encoding_format="float",
            )

            # Attach embeddings to chunks
            for i, chunk in enumerate(chunks):
                chunk.embedding = response.data[i].embedding

            logger.info(f"Generated embeddings for {len(chunks)} chunks")
            return chunks

        except Exception as e:
            logger.error(f"Batch embedding failed: {e}")
            raise

    async def embed_query(self, query: str) -> List[float]:
        """Generate embedding for a search query."""
        return await self.embed_text(query)


# Convenience function
async def get_embedder() -> Embedder:
    """Get embedder instance with config from settings."""
    from app.config import settings
    return Embedder(
        api_key=settings.OPENAI_API_KEY,
        model="text-embedding-3-small",
    )