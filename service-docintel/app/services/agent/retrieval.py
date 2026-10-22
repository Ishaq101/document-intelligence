"""Dense, BM25-style sparse, and RRF retrieval from Qdrant."""
import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Optional
from uuid import UUID

from app.models.chunk import ChunkResponse
from app.services.ingestion.embedder import get_embedder
from app.services.storage.qdrant import QdrantManager, SearchResult

logger = logging.getLogger(__name__)


async def select_category(query: str) -> Optional[str]:
    """Choose one admin category whose description matches the query."""
    from app.services.llm_client import get_openai_client
    from app.services.storage.postgres import list_categories

    categories = await list_categories()
    if not categories:
        return None

    client = get_openai_client()
    category_guide = "\n".join(
        f"- {category['name']}: {category['description']}" for category in categories
    )
    try:
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Select the single document category most relevant to the question. "
                        "Use category descriptions as routing rules. Return JSON with category "
                        "set to an exact listed name, or null when no category clearly applies.\n\n"
                        f"Categories:\n{category_guide}"
                    ),
                },
                {"role": "user", "content": query},
            ],
            temperature=0,
            response_format={"type": "json_object"},
            max_tokens=100,
        )
        selected = json.loads(response.choices[0].message.content).get("category")
        valid_names = {category["name"] for category in categories}
        return selected if selected in valid_names else None
    except Exception:
        logger.exception("Category selection failed; retrieving without category filter")
        return None


@dataclass
class RetrievalResult:
    chunks: list[ChunkResponse]
    scores: list[float]
    method: str


def to_chunks(results: list[SearchResult]) -> RetrievalResult:
    return RetrievalResult(
        chunks=[
            ChunkResponse(
                chunk_id=UUID(result["chunk_id"]),
                file_id=UUID(result["file_id"]),
                filename=result["filename"],
                page=result["page"],
                category=result["category"],
                company=result["company"],
                content=result["content"],
                created_at=None,
            )
            for result in results
        ],
        scores=[result["score"] for result in results],
        method="",
    )


async def vector_search(
    query: str,
    top_k: int = 5,
    category: Optional[str] = None,
) -> RetrievalResult:
    """Retrieve by dense embedding from Qdrant."""
    query_vector = await (await get_embedder()).embed_query(query)
    result = to_chunks(await QdrantManager.search(query_vector, top_k, category))
    result.method = "vector"
    return result


async def bm25_search(
    query: str,
    top_k: int = 5,
    category: Optional[str] = None,
) -> RetrievalResult:
    """Retrieve by deterministic BM25-style sparse vector from Qdrant."""
    result = to_chunks(await QdrantManager.search_sparse(query, top_k, category))
    result.method = "bm25"
    return result


def reciprocal_rank_fusion(results: list[RetrievalResult], top_k: int, k: int = 60) -> RetrievalResult:
    """Fuse dense and sparse rankings using reciprocal rank fusion."""
    scores: dict[UUID, float] = {}
    chunks: dict[UUID, ChunkResponse] = {}
    for result in results:
        for rank, chunk in enumerate(result.chunks, start=1):
            scores[chunk.chunk_id] = scores.get(chunk.chunk_id, 0.0) + 1 / (k + rank)
            chunks[chunk.chunk_id] = chunk

    ranking = sorted(scores, key=scores.get, reverse=True)[:top_k]
    return RetrievalResult(
        chunks=[chunks[chunk_id] for chunk_id in ranking],
        scores=[scores[chunk_id] for chunk_id in ranking],
        method="hybrid_rrf",
    )


class RetrievalOrchestrator:
    def __init__(self, method: str = "hybrid_rrf", top_k: int = 5):
        self.method = method
        self.top_k = top_k

    async def retrieve(
        self,
        query: str,
        user_id: UUID,
        category: Optional[str] = None,
        top_k: Optional[int] = None,
    ) -> RetrievalResult:
        """Retrieve only chunks belonging to ingested Qdrant collection."""
        del user_id  # Qdrant collection holds chunks from seed-admin ingestion.
        limit = top_k or self.top_k
        if self.method == "vector":
            return await vector_search(query, limit, category)
        if self.method == "bm25":
            return await bm25_search(query, limit, category)
        if self.method != "hybrid_rrf":
            logger.warning("Unknown retrieval method %s; using hybrid_rrf", self.method)

        dense, sparse = await asyncio.gather(
            vector_search(query, limit, category),
            bm25_search(query, limit, category),
        )
        return reciprocal_rank_fusion([dense, sparse], limit)


async def get_retrieval_orchestrator(
    method: Optional[str] = None,
    top_k: Optional[int] = None,
) -> RetrievalOrchestrator:
    """Create retrieval service from persisted admin configuration."""
    if method is None or top_k is None:
        from app.services.storage.postgres import get_admin_config

        config = await get_admin_config()
        method = method or config.get("retrieval_method", "hybrid_rrf")
        top_k = top_k or config.get("top_k", 5)
    return RetrievalOrchestrator(method, top_k)