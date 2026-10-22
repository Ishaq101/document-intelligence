"""Evidence sufficiency evaluation and bounded retrieval retry."""
import logging
from typing import Optional
from uuid import UUID

from app.models.agent import EvidenceStatus
from app.services.agent.retrieval import (
    RetrievalResult,
    get_retrieval_orchestrator,
    select_category,
)

logger = logging.getLogger(__name__)


class EvidenceEvaluator:
    """Evaluate result availability and method-compatible relevance scores."""

    def __init__(self, min_chunks: int = 1, min_score_threshold: float = 0.3):
        self.min_chunks = min_chunks
        self.min_score_threshold = min_score_threshold

    def evaluate(self, query: str, retrieval_result: RetrievalResult) -> EvidenceStatus:
        if not retrieval_result.chunks:
            logger.info("No chunks retrieved for query: %s", query[:100])
            return EvidenceStatus.NOT_RELEVANT

        # RRF produces rank-fusion scores near 1/60, not similarity scores.
        if retrieval_result.method == "hybrid_rrf":
            return (
                EvidenceStatus.SUFFICIENT
                if len(retrieval_result.chunks) >= self.min_chunks
                else EvidenceStatus.NOT_SUFFICIENT
            )

        relevant_chunks = sum(
            score >= self.min_score_threshold for score in retrieval_result.scores
        )
        if relevant_chunks == 0:
            return EvidenceStatus.NOT_RELEVANT
        if relevant_chunks >= self.min_chunks:
            return EvidenceStatus.SUFFICIENT
        return EvidenceStatus.NOT_SUFFICIENT

    def rephrase_query(self, query: str, attempt: int) -> str:
        templates = (
            "What information is available about: {query}",
            "Find details regarding: {query}",
        )
        return templates[attempt - 1].format(query=query) if attempt <= len(templates) else query


class RetrievalWithRetry:
    """Retrieve evidence and retry at most twice when it is insufficient."""

    def __init__(
        self,
        max_retries: int = 2,
        min_chunks: int = 1,
        min_score_threshold: float = 0.3,
    ):
        self.max_retries = max_retries
        self.evaluator = EvidenceEvaluator(min_chunks, min_score_threshold)

    async def retrieve_with_evaluation(
        self,
        query: str,
        user_id: UUID,
        category: Optional[str] = None,
        top_k: int = 5,
        method: Optional[str] = None,
    ) -> tuple[RetrievalResult, EvidenceStatus, Optional[str]]:
        orchestrator = await get_retrieval_orchestrator(method=method, top_k=top_k)
        category = category or await select_category(query)
        if category:
            logger.info("Retrieval category selected: %s", category)
        current_query = query
        rephrased_query: Optional[str] = None
        result = RetrievalResult(chunks=[], scores=[], method=orchestrator.method)

        for attempt in range(self.max_retries + 1):
            result = await orchestrator.retrieve(current_query, user_id, category, top_k)
            status = self.evaluator.evaluate(current_query, result)
            if status == EvidenceStatus.SUFFICIENT or attempt == self.max_retries:
                return result, status, rephrased_query

            current_query = self.evaluator.rephrase_query(query, attempt + 1)
            rephrased_query = current_query
            logger.info("Retrying retrieval with rephrased query, attempt %s", attempt + 1)

        return result, EvidenceStatus.NOT_RELEVANT, rephrased_query


async def evaluate_evidence(
    query: str,
    retrieval_result: RetrievalResult,
    min_chunks: int = 1,
    min_score_threshold: float = 0.3,
) -> EvidenceStatus:
    """Evaluate one retrieval result."""
    return EvidenceEvaluator(min_chunks, min_score_threshold).evaluate(query, retrieval_result)
