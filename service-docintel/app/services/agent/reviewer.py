"""Post-generation review - correctness, grounded, clean_format, PII masking."""
import logging
import json
import re
from typing import List, Optional
from dataclasses import dataclass

from app.models.agent import AgentResponse, Citation, ReviewResult
from app.models.chunk import ChunkResponse
from app.services.llm_client import get_openai_client

logger = logging.getLogger(__name__)


class AnswerReviewer:
    """Reviews generated answers for quality and safety."""

    SYSTEM_PROMPT = """You are a quality reviewer for a document intelligence system.
Review the generated answer against the source chunks and check for:

1. CORRECTNESS: Is the answer factually correct based on the source chunks?
2. GROUNDED: Are all claims in the answer supported by the source chunks?
3. CLEAN_FORMAT: Is the answer well-formatted, readable, and free of artifacts?
4. PII: Does the answer contain any personally identifiable information?

Respond with JSON only:
{
  "correctness": boolean,
  "grounded": boolean,
  "clean_format": boolean,
  "contain_pii": boolean,
  "repaired_answer": "string (if any issues found, provide corrected version)"
}"""

    def __init__(self):
        self._client = None

    @property
    def client(self):
        if self._client is None:
            self._client = get_openai_client()
        return self._client

    def _format_context(self, chunks: List[ChunkResponse]) -> str:
        """Format chunks for review context."""
        context_parts = []
        for i, chunk in enumerate(chunks):
            context_parts.append(
                f"[Source {i+1}] {chunk.filename}, Page {chunk.page}: {chunk.content[:500]}..."
            )
        return "\n".join(context_parts)

    def _check_pii_basic(self, text: str) -> bool:
        """Basic PII check using regex patterns."""
        pii_patterns = [
            r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',  # email
            r'\b\d{3}-\d{2}-\d{4}\b',  # SSN
            r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b',  # credit card
            r'\b(?:\+?1[-.\s]?)?\(?([0-9]{3})\)?[-.\s]?([0-9]{3})[-.\s]?([0-9]{4})\b',  # phone
        ]
        for pattern in pii_patterns:
            if re.search(pattern, text):
                return True
        return False

    async def review(
        self,
        answer: AgentResponse,
        chunks: List[ChunkResponse],
    ) -> ReviewResult:
        """Review the generated answer."""
        # Quick checks first
        has_pii = self._check_pii_basic(answer.answer)

        # Check citation validity
        valid_citations = True
        cited_chunk_ids = {str(c.chunk_id) for c in answer.citations}
        available_chunk_ids = {str(c.chunk_id) for c in chunks}
        if not cited_chunk_ids.issubset(available_chunk_ids):
            valid_citations = False

        # For thorough review, use LLM
        try:
            context = self._format_context(chunks)

            review_prompt = f"""{self.SYSTEM_PROMPT}

Answer to review:
{answer.answer}

Citations provided:
{json.dumps([{"filename": c.filename, "page": c.page, "chunk_id": str(c.chunk_id)} for c in answer.citations])}

Source chunks:
{context}

Provide your review as JSON."""

            response = await self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user", "content": review_prompt},
                ],
                temperature=0,
                response_format={"type": "json_object"},
                max_tokens=500,
            )

            result = json.loads(response.choices[0].message.content)

            # Override PII check with our basic check
            result["contain_pii"] = has_pii or result.get("contain_pii", False)

            return ReviewResult(
                correctness=result.get("correctness", True),
                grounded=result.get("grounded", valid_citations),
                clean_format=result.get("clean_format", True),
                contain_pii=result["contain_pii"],
                repaired_answer=result.get("repaired_answer"),
            )

        except Exception as e:
            logger.error(f"LLM review failed: {e}, using basic checks")
            return ReviewResult(
                correctness=True,
                grounded=valid_citations,
                clean_format=True,
                contain_pii=has_pii,
                repaired_answer=None,
            )


async def review_answer(
    answer: AgentResponse,
    chunks: List[ChunkResponse],
) -> ReviewResult:
    """Review answer for quality and safety."""
    reviewer = AnswerReviewer()
    return await reviewer.review(answer, chunks)


def repair_answer_if_needed(
    answer: AgentResponse,
    review: ReviewResult,
) -> AgentResponse:
    """Apply repairs if review found issues."""
    if review.repaired_answer and (not review.correctness or not review.grounded or review.contain_pii):
        return AgentResponse(
            answer=review.repaired_answer,
            citations=answer.citations,
            confidence=answer.confidence,
            evidence_sufficient=answer.evidence_sufficient,
            language=answer.language,
        )
    return answer