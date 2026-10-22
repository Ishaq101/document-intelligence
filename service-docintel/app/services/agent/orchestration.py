"""Main agent orchestration orchestrating guardrails, intent, retrieval, generation, and review."""

import logging
import time
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from uuid import UUID

from app.models.agent import (
    AgentResponse,
    EvidenceStatus,
    IntentClassification,
    ReviewResult,
    TaskType,
)
from app.services.agent.evidence import RetrievalWithRetry
from app.services.agent.generator import AnswerGenerator
from app.services.agent.guardrails import run_guardrails
from app.services.agent.intent import classify_intent
from app.services.agent.reviewer import repair_answer_if_needed, review_answer
from app.services.agent.tasks import execute_task
from app.services.observability.langfuse import TimedSpan
from app.services.storage.postgres import add_message, get_admin_config

logger = logging.getLogger(__name__)


@dataclass
class OrchestrationResult:
    answer: AgentResponse
    intent: IntentClassification
    evidence_status: EvidenceStatus
    review: ReviewResult
    runtime_ms: int
    rephrased_query: str | None = None


class AgentOrchestration:
    """Main agent orchestration orchestrator."""

    def __init__(self) -> None:
        """Tracing is ambient: spans attach to the active chat trace when one exists."""

    async def generate_answer(
        self,
        question: str,
        session_id: UUID,
        user_id: UUID,
    ) -> OrchestrationResult:
        """Generate answer through the full agent pipeline (non-streaming)."""
        start_time = time.perf_counter()

        # Step 1: Guardrails
        with TimedSpan("guardrails", {"cleaned_length": len(question)}, as_type="guardrail"):
            guardrail_passed, refusal_reason, cleaned_question = await run_guardrails(question)

            if not guardrail_passed:
                return OrchestrationResult(
                    answer=AgentResponse(
                        answer=f"I cannot process this request: {refusal_reason}",
                        citations=[],
                        confidence="low",
                        evidence_sufficient=False,
                    ),
                    intent=IntentClassification(
                        need_plan=False, social_question=False, task_types=[], language="en"
                    ),
                    evidence_status=EvidenceStatus.NOT_RELEVANT,
                    review=ReviewResult(
                        correctness=False, grounded=False, clean_format=True, contain_pii=False
                    ),
                    runtime_ms=int((time.perf_counter() - start_time) * 1000),
                )

        # Step 2: Intent Classification
        with TimedSpan("intent_classification", {"cleaned_length": len(cleaned_question)}):
            intent = await classify_intent(cleaned_question)

        # Handle social questions
        if intent.social_question:
            social_answer = "Hello! How can I help you with your documents today?"
            runtime_ms = int((time.perf_counter() - start_time) * 1000)
            await add_message(session_id, "assistant", social_answer, runtime_ms=runtime_ms)
            return OrchestrationResult(
                answer=AgentResponse(
                    answer=social_answer,
                    citations=[],
                    confidence="high",
                    evidence_sufficient=True,
                    language=intent.language,
                ),
                intent=intent,
                evidence_status=EvidenceStatus.SUFFICIENT,
                review=ReviewResult(
                    correctness=True, grounded=True, clean_format=True, contain_pii=False
                ),
                runtime_ms=runtime_ms,
            )

        # Step 3: Execute tasks based on intent
        chunks = []
        task_results = {}

        for task_type in intent.task_types:
            with TimedSpan(f"task_{task_type.value}", {"task_type": task_type.value}):
                if task_type == TaskType.DOCUMENT_METADATA:
                    result = await execute_task(task_type, user_id=user_id)
                    task_results[task_type] = result
                    # For metadata, we don't need chunks

                elif task_type == TaskType.SUMMARY:
                    result = await execute_task(task_type, session_id=session_id, user_id=user_id)
                    task_results[task_type] = result

                elif task_type == TaskType.KNOWLEDGE_RETRIEVAL:
                    # Retrieve with evidence evaluation
                    admin_config = await get_admin_config()
                    retrieval = RetrievalWithRetry()

                    (
                        retrieval_result,
                        evidence_status,
                        rephrased,
                    ) = await retrieval.retrieve_with_evaluation(
                        query=cleaned_question,
                        user_id=user_id,
                        top_k=admin_config.get("top_k", 5),
                        method=admin_config.get("retrieval_method", "hybrid_rrf"),
                    )

                    chunks = retrieval_result.chunks
                    task_results[task_type] = {
                        "chunks": chunks,
                        "evidence_status": evidence_status,
                        "rephrased_query": rephrased,
                    }

        # Determine overall evidence status
        evidence_status = EvidenceStatus.SUFFICIENT
        rephrased_query = None
        for task_type, result in task_results.items():
            if task_type == TaskType.KNOWLEDGE_RETRIEVAL:
                evidence_status = result["evidence_status"]
                rephrased_query = result.get("rephrased_query")
                break

        # If no knowledge retrieval task, but we have metadata/summary results
        if TaskType.KNOWLEDGE_RETRIEVAL not in intent.task_types:
            # Generate response from task results directly
            answer_text = self._format_task_results(task_results, intent.task_types)
            answer = AgentResponse(
                answer=answer_text,
                citations=[],
                confidence="high",
                evidence_sufficient=True,
                language=intent.language,
            )
        else:
            # Step 4: Generate answer with citations
            with TimedSpan("generation", {"chunks": len(chunks)}):
                generator = AnswerGenerator()
                answer = await generator.generate(
                    question=cleaned_question,
                    chunks=chunks,
                    task_type=TaskType.KNOWLEDGE_RETRIEVAL,
                    language=intent.language,
                )

        # Metadata and summary are generated from persisted records, not retrieved chunks.
        if TaskType.KNOWLEDGE_RETRIEVAL in intent.task_types:
            with TimedSpan("review", {}):
                review = await review_answer(answer, chunks)
            if review.repaired_answer:
                answer = repair_answer_if_needed(answer, review)
        else:
            review = ReviewResult(
                correctness=True,
                grounded=True,
                clean_format=True,
                contain_pii=False,
            )

        # Store assistant message with runtime
        runtime_ms = int((time.perf_counter() - start_time) * 1000)
        citations_json = [citation.model_dump(mode="json") for citation in answer.citations]
        await add_message(session_id, "assistant", answer.answer, citations_json, runtime_ms)

        return OrchestrationResult(
            answer=answer,
            intent=intent,
            evidence_status=evidence_status,
            review=review,
            runtime_ms=runtime_ms,
            rephrased_query=rephrased_query,
        )

    async def generate_answer_stream(
        self,
        question: str,
        session_id: UUID,
        user_id: UUID,
    ) -> AsyncGenerator[dict, None]:
        """Generate answer with streaming response."""
        start_time = time.perf_counter()

        # Step 1: Guardrails
        with TimedSpan("guardrails", {"cleaned_length": len(question)}, as_type="guardrail"):
            guardrail_passed, refusal_reason, cleaned_question = await run_guardrails(question)

            if not guardrail_passed:
                yield {
                    "type": "error",
                    "message": f"I cannot process this request: {refusal_reason}",
                }
                return

        # Step 2: Intent Classification
        with TimedSpan("intent_classification", {"cleaned_length": len(cleaned_question)}):
            intent = await classify_intent(cleaned_question)

        # Handle social questions.
        if intent.social_question:
            social_answer = "Hello! How can I help you with your documents today?"
            runtime_ms = int((time.perf_counter() - start_time) * 1000)
            await add_message(session_id, "assistant", social_answer, runtime_ms=runtime_ms)
            yield {"type": "token", "content": social_answer}
            yield {"type": "done", "answer": social_answer}
            return

        # Step 3: Execute tasks
        chunks = []
        task_results = {}
        evidence_status = EvidenceStatus.SUFFICIENT

        for task_type in intent.task_types:
            with TimedSpan(f"task_{task_type.value}", {"task_type": task_type.value}):
                if task_type == TaskType.DOCUMENT_METADATA:
                    result = await execute_task(task_type, user_id=user_id)
                    task_results[task_type] = result

                elif task_type == TaskType.SUMMARY:
                    result = await execute_task(task_type, session_id=session_id, user_id=user_id)
                    task_results[task_type] = result

                elif task_type == TaskType.KNOWLEDGE_RETRIEVAL:
                    admin_config = await get_admin_config()
                    retrieval = RetrievalWithRetry()

                    (
                        retrieval_result,
                        evidence_status,
                        rephrased,
                    ) = await retrieval.retrieve_with_evaluation(
                        query=cleaned_question,
                        user_id=user_id,
                        top_k=admin_config.get("top_k", 5),
                        method=admin_config.get("retrieval_method", "hybrid_rrf"),
                    )

                    chunks = retrieval_result.chunks
                    task_results[task_type] = {
                        "chunks": chunks,
                        "evidence_status": evidence_status,
                        "rephrased_query": rephrased,
                    }

        # Stream response
        if TaskType.KNOWLEDGE_RETRIEVAL not in intent.task_types:
            # Format task results directly.
            answer_text = self._format_task_results(task_results, intent.task_types)
            runtime_ms = int((time.perf_counter() - start_time) * 1000)
            await add_message(session_id, "assistant", answer_text, runtime_ms=runtime_ms)
            yield {"type": "token", "content": answer_text}
            yield {"type": "done", "answer": answer_text}
            return
        # Stream generation.
        generator = AnswerGenerator()
        full_answer = ""
        async for chunk in generator.generate_stream(
            cleaned_question, chunks, TaskType.KNOWLEDGE_RETRIEVAL, intent.language
        ):
            if chunk["type"] == "token":
                full_answer += chunk["content"]
                yield chunk
            elif chunk["type"] == "done":
                full_answer = chunk["answer"]

        # Review complete answer before persisting it.
        if chunks:
            with TimedSpan("review", {}):
                temp_answer = AgentResponse(
                    answer=full_answer,
                    citations=[],
                    confidence="medium",
                    evidence_sufficient=evidence_status == EvidenceStatus.SUFFICIENT,
                    language=intent.language,
                )
                await review_answer(temp_answer, chunks)

        runtime_ms = int((time.perf_counter() - start_time) * 1000)
        await add_message(session_id, "assistant", full_answer, [], runtime_ms)
        yield {"type": "done", "answer": full_answer}

    def _format_task_results(self, task_results: dict, task_types: list[TaskType]) -> str:
        """Format task results into a readable answer."""
        parts = []

        for task_type in task_types:
            result = task_results.get(task_type)
            if result is None:
                continue

            if task_type == TaskType.DOCUMENT_METADATA:
                if isinstance(result, dict):
                    parts.append(result.get("message", ""))
                else:
                    parts.append(str(result))

            elif task_type == TaskType.SUMMARY:
                parts.append(str(result))

        return "\n\n".join(parts) if parts else "I couldn't find any relevant information."
