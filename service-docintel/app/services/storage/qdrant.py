import hashlib
import logging
import re
from typing import Optional, TypedDict
from uuid import UUID

from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import UnexpectedResponse
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PayloadSchemaType,
    PointStruct,
    SparseVector,
    SparseVectorParams,
    ScoredPoint,
    VectorParams,
)

from app.config import settings
from app.services.ingestion.chunker import Chunk

logger = logging.getLogger(__name__)
_TOKEN_PATTERN = re.compile(r"\b[\w-]+\b", re.UNICODE)


class SearchResult(TypedDict):
    chunk_id: str
    score: float
    filename: str
    file_id: str
    page: int
    category: Optional[str]
    company: Optional[str]
    content: str


class QdrantManager:
    _client: Optional[QdrantClient] = None

    @classmethod
    def get_client(cls) -> QdrantClient:
        if cls._client is None:
            cls._client = QdrantClient(
                url=settings.QDRANT_ENDPOINT,
                api_key=settings.QDRANT_API_KEY,
                timeout=60,
            )
            logger.info("Qdrant client initialized")
        return cls._client

    @staticmethod
    def _sparse_vector(text: str) -> SparseVector:
        """Make deterministic hashed term-frequency sparse vector."""
        frequencies: dict[int, float] = {}
        for token in _TOKEN_PATTERN.findall(text.lower()):
            index = int.from_bytes(hashlib.sha256(token.encode()).digest()[:4], "big")
            frequencies[index] = frequencies.get(index, 0.0) + 1.0
        return SparseVector(indices=list(frequencies), values=list(frequencies.values()))

    @staticmethod
    def _category_filter(category: Optional[str]) -> Optional[Filter]:
        if category is None:
            return None
        return Filter(must=[FieldCondition(key="category", match=MatchValue(value=category))])

    @classmethod
    async def initialize_collection(cls) -> None:
        """Create dense and sparse-vector collection plus filter indexes."""
        client = cls.get_client()
        collection_name = settings.QDRANT_COLLECTION

        try:
            client.get_collection(collection_name)
            logger.info("Collection %s already exists", collection_name)
        except UnexpectedResponse:
            client.create_collection(
                collection_name=collection_name,
                vectors_config={
                    "dense": VectorParams(
                        size=settings.EMBEDDING_DIMENSION,
                        distance=Distance.COSINE,
                    )
                },
                sparse_vectors_config={"bm25": SparseVectorParams()},
            )
            logger.info("Created collection %s", collection_name)

        for field_name, field_type in (
            ("filename", PayloadSchemaType.KEYWORD),
            ("file_id", PayloadSchemaType.KEYWORD),
            ("page", PayloadSchemaType.INTEGER),
            ("category", PayloadSchemaType.KEYWORD),
            ("company", PayloadSchemaType.KEYWORD),
        ):
            try:
                client.create_payload_index(
                    collection_name=collection_name,
                    field_name=field_name,
                    field_schema=field_type,
                )
            except Exception as error:
                logger.warning("Could not create index for %s: %s", field_name, error)

    @classmethod
    async def upsert_chunks(cls, chunks: list[Chunk], category: Optional[str] = None) -> None:
        """Store chunks with dense and sparse vectors in Qdrant."""
        points: list[PointStruct] = []
        for chunk in chunks:
            if chunk.embedding is None:
                raise ValueError(f"Chunk {chunk.chunk_id} has no embedding")
            points.append(
                PointStruct(
                    id=chunk.chunk_id,
                    vector={
                        "dense": chunk.embedding,
                        "bm25": cls._sparse_vector(chunk.content),
                    },
                    payload={
                        "filename": chunk.filename,
                        "file_id": chunk.file_id,
                        "page": chunk.page,
                        "category": category or chunk.category,
                        "company": chunk.company,
                        "content": chunk.content,
                        "detected_page_type": chunk.metadata.get("detected_page_type"),
                        "actual_parser": chunk.metadata.get("actual_parser"),
                    },
                )
            )

        if points:
            cls.get_client().upsert(
                collection_name=settings.QDRANT_COLLECTION,
                points=points,
                wait=True,
            )
            logger.info("Upserted %s chunks to Qdrant", len(points))

    @classmethod
    async def delete_document_chunks(cls, file_id: UUID) -> None:
        """Delete all vectors belonging to one document."""
        cls.get_client().delete(
            collection_name=settings.QDRANT_COLLECTION,
            wait=True,
            points_selector=Filter(
                must=[FieldCondition(key="file_id", match=MatchValue(value=str(file_id)))]
            ),
        )

    @classmethod
    async def count_document_chunks(cls, file_id: UUID) -> int:
        """Return vector count for one document before deletion."""
        result = cls.get_client().count(
            collection_name=settings.QDRANT_COLLECTION,
            count_filter=Filter(
                must=[FieldCondition(key="file_id", match=MatchValue(value=str(file_id)))]
            ),
            exact=True,
        )
        return result.count

    @classmethod
    def _search_results(cls, results: list[ScoredPoint]) -> list[SearchResult]:
        return [
            SearchResult(
                chunk_id=str(result.id),
                score=result.score,
                filename=str(result.payload["filename"]),
                file_id=str(result.payload["file_id"]),
                page=int(result.payload["page"]),
                category=str(result.payload["category"]) if result.payload.get("category") else None,
                company=str(result.payload["company"]) if result.payload.get("company") else None,
                content=str(result.payload["content"]),
            )
            for result in results
        ]

    @classmethod
    async def search(
        cls,
        query_vector: list[float],
        top_k: int = 5,
        category: Optional[str] = None,
    ) -> list[SearchResult]:
        """Search dense vectors, optionally constrained to one category."""
        response = cls.get_client().query_points(
            collection_name=settings.QDRANT_COLLECTION,
            query=query_vector,
            using="dense",
            query_filter=cls._category_filter(category),
            limit=top_k,
            with_payload=True,
            with_vectors=False,
        )
        return cls._search_results(response.points)

    @classmethod
    async def search_sparse(
        cls,
        query: str,
        top_k: int = 5,
        category: Optional[str] = None,
    ) -> list[SearchResult]:
        """Search hashed BM25-style sparse vectors from same Qdrant collection."""
        response = cls.get_client().query_points(
            collection_name=settings.QDRANT_COLLECTION,
            query=cls._sparse_vector(query),
            using="bm25",
            query_filter=cls._category_filter(category),
            limit=top_k,
            with_payload=True,
            with_vectors=False,
        )
        return cls._search_results(response.points)

    @classmethod
    async def close(cls) -> None:
        if cls._client:
            cls._client.close()
            cls._client = None