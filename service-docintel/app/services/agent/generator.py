"""Answer generator with structured output and citations using OpenAI."""
import logging
import json
from typing import List, Optional, AsyncGenerator
from uuid import UUID

from app.models.agent import AgentResponse, Citation, TaskType
from app.models.chunk import ChunkResponse
from app.services.llm_client import get_openai_client

logger = logging.getLogger(__name__)


class AnswerGenerator:
    """Generates answers with citations using OpenAI structured output."""

    SYSTEM_PROMPT = """You are a document intelligence assistant. Answer questions based ONLY on the provided context chunks.

Instructions:
1. Use ONLY the information from the provided chunks to answer
2. Cite sources using only chunk_id values supplied in context; never invent a UUID
3. If the context doesn't contain enough information, say so honestly
4. Keep answers concise but complete
5. Use the same language as the question
6. Return a human-readable answer in plain text. Never output JSON, XML, YAML, or code unless the user explicitly asks for it.
7. Do NOT include inline source markers like [Chunk 1], [1], or (Source: ...) in your answer text. Citations are tracked separately. Write the answer as clean prose.

Context chunks will be provided with their source filename, page number, and content."""

    def __init__(self):
        self._client = None

    @property
    def client(self):
        if self._client is None:
            self._client = get_openai_client()
        return self._client

    def _format_context(self, chunks: List[ChunkResponse]) -> str:
        """Format chunks as context for the LLM."""
        context_parts = []
        for i, chunk in enumerate(chunks):
            context_parts.append(
                f"[Chunk {i+1}] ID: {chunk.chunk_id}, Source: {chunk.filename}, Page: {chunk.page}\n"
                f"Content: {chunk.content}\n"
            )
        return "\n".join(context_parts)

    def _build_prompt(self, question: str, chunks: List[ChunkResponse], task_type: TaskType) -> str:
        """Build the prompt based on task type."""
        context = self._format_context(chunks)

        if task_type == TaskType.DOCUMENT_METADATA:
            return f"{self.SYSTEM_PROMPT}\n\nQuestion: {question}\n\nContext:\n{context}\n\nProvide a concise answer about the document metadata."
        elif task_type == TaskType.SUMMARY:
            return f"{self.SYSTEM_PROMPT}\n\nQuestion: {question}\n\nContext:\n{context}\n\nProvide a concise summary."
        else:  # KNOWLEDGE_RETRIEVAL
            return f"{self.SYSTEM_PROMPT}\n\nQuestion: {question}\n\nContext:\n{context}\n\nAnswer the question based on the context above."

    async def generate(
        self,
        question: str,
        chunks: List[ChunkResponse],
        task_type: TaskType = TaskType.KNOWLEDGE_RETRIEVAL,
        language: str = "en",
    ) -> AgentResponse:
        """Generate answer with citations."""
        prompt = self._build_prompt(question, chunks, task_type)

        try:
            response = await self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": question},
                ],
                temperature=0.1,
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "agent_response",
                        "schema": {
                            "type": "object",
                            "properties": {
                                "answer": {"type": "string"},
                                "citations": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "filename": {"type": "string"},
                                            "page": {"type": "integer"},
                                            "chunk_id": {"type": "string", "format": "uuid"},
                                            "excerpt": {"type": "string"},
                                        },
                                        "required": ["filename", "page", "chunk_id"],
                                    },
                                },
                                "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                                "evidence_sufficient": {"type": "boolean"},
                                "language": {"type": "string"},
                            },
                            "required": ["answer", "citations", "confidence", "evidence_sufficient", "language"],
                        },
                    },
                },
                max_tokens=1500,
            )

            result = json.loads(response.choices[0].message.content)

            # Accept citations only when they reference supplied chunks.
            chunks_by_id = {str(chunk.chunk_id): chunk for chunk in chunks}
            citations: list[Citation] = []
            for raw_citation in result.get("citations", []):
                raw_chunk_id = raw_citation.get("chunk_id")
                source_chunk = chunks_by_id.get(raw_chunk_id)
                if source_chunk is None:
                    logger.warning("Ignoring citation for unknown chunk ID: %s", raw_chunk_id)
                    continue
                citations.append(
                    Citation(
                        filename=source_chunk.filename,
                        page=source_chunk.page,
                        chunk_id=source_chunk.chunk_id,
                        excerpt=raw_citation.get("excerpt"),
                    )
                )

            return AgentResponse(
                answer=result["answer"],
                citations=citations,
                confidence=result.get("confidence", "medium"),
                evidence_sufficient=result.get("evidence_sufficient", True),
                language=result.get("language", language),
            )

        except Exception as e:
            logger.error(f"Answer generation failed: {e}")
            # Fallback response
            return AgentResponse(
                answer="I apologize, but I encountered an error generating the answer. Please try again.",
                citations=[],
                confidence="low",
                evidence_sufficient=False,
                language=language,
            )

    async def generate_stream(
        self,
        question: str,
        chunks: List[ChunkResponse],
        task_type: TaskType = TaskType.KNOWLEDGE_RETRIEVAL,
        language: str = "en",
    ) -> AsyncGenerator[dict, None]:
        """Generate streaming answer with citations."""
        prompt = self._build_prompt(question, chunks, task_type)

        try:
            stream = await self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": question},
                ],
                temperature=0.1,
                stream=True,
                stream_options={"include_usage": True},
                max_tokens=1500,
            )

            full_answer = ""
            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    content = chunk.choices[0].delta.content
                    full_answer += content
                    yield {"type": "token", "content": content}

            # After streaming, generate citations separately (simplified)
            # In production, you'd want structured output with streaming
            yield {"type": "citations", "citations": []}
            yield {"type": "done", "answer": full_answer}

        except Exception as e:
            logger.error(f"Streaming generation failed: {e}")
            yield {"type": "error", "message": str(e)}


# Convenience function
async def generate_answer(
    question: str,
    chunks: List[ChunkResponse],
    task_type: TaskType = TaskType.KNOWLEDGE_RETRIEVAL,
    language: str = "en",
) -> AgentResponse:
    """Generate answer with citations."""
    generator = AnswerGenerator()
    return await generator.generate(question, chunks, task_type, language)