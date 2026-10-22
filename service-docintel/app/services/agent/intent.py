"""Intent classification for the document agent using LLM for accurate context understanding."""
import logging
import json
from typing import List, Optional
from dataclasses import dataclass
from enum import Enum

from app.models.agent import TaskType, IntentClassification
from app.services.llm_client import get_openai_client

logger = logging.getLogger(__name__)


class IntentClassifier:
    """Classifies user intent using LLM for accurate context understanding."""

    SYSTEM_PROMPT = """You are an intent classifier for a document intelligence system.
Classify the user's question into one or more task types and determine if it's a social question.

Task types:
- document_metadata: Questions about available knowledge, document counts, listings, or file names (e.g., "what knowledge do you have", "how many files", "list all documents")
- knowledge_retrieval: Questions seeking information from documents (e.g., "what does the report say about X", "find information about Y")
- summary: Requests to summarize documents or conversations (e.g., "summarize the report", "give me a brief overview")

Social questions: Greetings, thanks, goodbyes, casual conversation (e.g., "hello", "thanks", "how are you")

Respond with JSON only:
{
  "need_plan": boolean,
  "social_question": boolean,
  "task_types": ["task_type1", "task_type2"],
  "language": "language_code"
}

need_plan: true if the question requires multi-step reasoning or multiple task types
social_question: true if it's a casual/conversational question
task_types: array of applicable task types
language: detected language code (en, id, etc.)"""

    def __init__(self):
        self._client = None

    @property
    def client(self):
        if self._client is None:
            self._client = get_openai_client()
        return self._client

    async def classify(self, question: str, language: str = "en") -> IntentClassification:
        """Classify the intent of a user question using LLM."""
        if question.lower().strip() in {"what knowledge do you have?", "what knowledge do you have"}:
            return IntentClassification(
                need_plan=False,
                social_question=False,
                task_types=[TaskType.DOCUMENT_METADATA],
                language=language,
            )
        try:
            response = await self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user", "content": question},
                ],
                temperature=0,
                response_format={"type": "json_object"},
                max_tokens=200,
            )

            result = json.loads(response.choices[0].message.content)

            # Convert task type strings to enums
            task_types = []
            for tt in result.get("task_types", []):
                try:
                    task_types.append(TaskType(tt))
                except ValueError:
                    logger.warning(f"Unknown task type: {tt}")

            # Default to knowledge_retrieval if none detected
            if not task_types:
                task_types = [TaskType.KNOWLEDGE_RETRIEVAL]

            return IntentClassification(
                need_plan=result.get("need_plan", False),
                social_question=result.get("social_question", False),
                task_types=task_types,
                language=result.get("language", language),
            )

        except Exception as e:
            logger.error(f"LLM intent classification failed: {e}, falling back to keyword-based")
            return self._fallback_classify(question, language)

    def _fallback_classify(self, question: str, language: str = "en") -> IntentClassification:
        """Fallback keyword-based classification."""
        question_lower = question.lower().strip()

        METADATA_KEYWORDS = [
            "what knowledge do you have", "what knowledge", "available knowledge",
            "how many", "count", "total", "number of", "list all", "what files",
            "show files", "list documents", "what documents", "filenames", "file names",
        ]

        SUMMARY_KEYWORDS = [
            "summarize", "summary", "summarise", "brief", "overview", "tldr",
            "key points", "main points", "highlights", "recap",
        ]

        SOCIAL_KEYWORDS = [
            "hello", "hi", "hey", "thanks", "thank you", "bye", "goodbye",
            "how are you", "what's up", "nice", "good job", "great",
        ]

        RETRIEVAL_KEYWORDS = [
            "what", "who", "when", "where", "why", "how", "which",
            "explain", "describe", "tell me", "find", "search", "look up",
            "show me", "give me", "get me", "answer",
        ]

        is_social = any(kw in question_lower for kw in self.SOCIAL_KEYWORDS)
        if is_social and len(question_lower.split()) < 10:
            return IntentClassification(
                need_plan=False,
                social_question=True,
                task_types=[],
                language=language,
            )

        task_types = []

        if any(kw in question_lower for kw in METADATA_KEYWORDS):
            task_types.append(TaskType.DOCUMENT_METADATA)

        if any(kw in question_lower for kw in SUMMARY_KEYWORDS):
            task_types.append(TaskType.SUMMARY)

        if any(kw in question_lower for kw in RETRIEVAL_KEYWORDS):
            task_types.append(TaskType.KNOWLEDGE_RETRIEVAL)

        if TaskType.DOCUMENT_METADATA in task_types:
            task_types = [TaskType.DOCUMENT_METADATA]
        elif not task_types:
            task_types = [TaskType.KNOWLEDGE_RETRIEVAL]

        need_plan = len(task_types) > 1 or len(question.split()) > 20

        return IntentClassification(
            need_plan=need_plan,
            social_question=False,
            task_types=task_types,
            language=language,
        )


# Convenience function
async def classify_intent(question: str, language: str = "en") -> IntentClassification:
    """Classify user intent using LLM."""
    classifier = IntentClassifier()
    return await classifier.classify(question, language)