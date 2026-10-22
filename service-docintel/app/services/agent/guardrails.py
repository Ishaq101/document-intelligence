"""Guardrails for the document agent - PII, injection, NSFW, unsafe chars, language detection."""
import logging
import re
from typing import Optional, List
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class GuardrailType(str, Enum):
    PII = "pii"
    INJECTION = "injection"
    NSFW = "nsfw"
    UNSAFE_CHARS = "unsafe_chars"
    LANGUAGE = "language"


@dataclass
class GuardrailResult:
    passed: bool
    guardrail: GuardrailType
    reason: Optional[str] = None
    cleaned_input: Optional[str] = None


# PII Detection using regex patterns (simplified - production would use Presidio)
PII_PATTERNS = {
    "email": r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
    "phone": r'\b(?:\+?1[-.\s]?)?\(?([0-9]{3})\)?[-.\s]?([0-9]{3})[-.\s]?([0-9]{4})\b',
    "ssn": r'\b\d{3}-\d{2}-\d{4}\b',
    "credit_card": r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b',
    "ip_address": r'\b(?:\d{1,3}\.){3}\d{1,3}\b',
}


# Prompt injection patterns
INJECTION_PATTERNS = [
    r"ignore\s+(?:previous|above|all)\s+(?:instructions|prompts|rules)",
    r"disregard\s+(?:previous|above|all)\s+(?:instructions|prompts|rules)",
    r"system\s*:\s*you\s+are\s+now",
    r"pretend\s+to\s+be\s+(?:a|an|the)\s+\w+",
    r"act\s+as\s+(?:a|an|the)\s+\w+",
    r"you\s+are\s+(?:a|an|the)\s+\w+\s+(?:now|from\s+now)",
    r"forget\s+(?:your|all)\s+(?:instructions|identity|role)",
    r"new\s+(?:instructions|rules|prompt)",
    r"override\s+(?:previous|all)\s+(?:instructions|rules)",
    r"<trusted_content>",
    r"<safe_for_work>",
    r"</trusted_content>",
    r"</safe_for_work>",
]

# NSFW detection - simple keyword-based (production would use toxic-bert)
NSFW_KEYWORDS = [
    # This is a minimal set - production should use a proper classifier
    "explicit_sexual_content",  # placeholder for actual toxic-bert integration
]

SUPPORTED_LANGUAGES = {"en", "id", "zh-cn", "zh-tw", "ja", "ko", "es", "fr", "de"}


def detect_pii(text: str) -> GuardrailResult:
    """Detect PII in text using regex patterns."""
    for pii_type, pattern in PII_PATTERNS.items():
        matches = re.findall(pattern, text, re.IGNORECASE)
        if matches:
            return GuardrailResult(
                passed=False,
                guardrail=GuardrailType.PII,
                reason=f"Detected {pii_type}: {matches[:3]}",  # Limit output
            )
    return GuardrailResult(passed=True, guardrail=GuardrailType.PII)


def detect_injection(text: str) -> GuardrailResult:
    """Detect prompt injection/jailbreak attempts."""
    text_lower = text.lower()
    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, text_lower, re.IGNORECASE):
            return GuardrailResult(
                passed=False,
                guardrail=GuardrailType.INJECTION,
                reason=f"Detected potential injection pattern: {pattern}",
            )
    return GuardrailResult(passed=True, guardrail=GuardrailType.INJECTION)


def detect_nsfw(text: str) -> GuardrailResult:
    """Detect NSFW content using keyword matching (placeholder for toxic-bert)."""
    # In production, integrate with toxic-bert or similar classifier
    # For now, this is a stub that always passes
    text_lower = text.lower()
    for keyword in NSFW_KEYWORDS:
        if keyword in text_lower:
            return GuardrailResult(
                passed=False,
                guardrail=GuardrailType.NSFW,
                reason=f"Detected NSFW keyword: {keyword}",
            )
    return GuardrailResult(passed=True, guardrail=GuardrailType.NSFW)


def clean_unsafe_chars(text: str) -> GuardrailResult:
    """Clean unsafe characters and HTML-like tags that could be used for injection."""
    # Remove specific tags that could be used to manipulate the model
    unsafe_tags = [
        r"<trusted_content>",
        r"</trusted_content>",
        r"<safe_for_work>",
        r"</safe_for_work>",
    ]

    cleaned = text
    removed_tags = []

    for tag in unsafe_tags:
        if tag in cleaned:
            cleaned = cleaned.replace(tag, "")
            removed_tags.append(tag)

    # Strip HTML tags before escaping literal angle brackets for display safety.
    cleaned = re.sub(r"<[^>]+>", "", cleaned)

    if removed_tags:
        return GuardrailResult(
            passed=True,
            guardrail=GuardrailType.UNSAFE_CHARS,
            reason=f"Removed unsafe tags: {removed_tags}",
            cleaned_input=cleaned,
        )

    return GuardrailResult(
        passed=True,
        guardrail=GuardrailType.UNSAFE_CHARS,
        cleaned_input=cleaned,
    )


def detect_language(text: str) -> GuardrailResult:
    """Detect language when input has enough text for a reliable result."""
    if len(re.findall(r"\w+", text, re.UNICODE)) < 3:
        return GuardrailResult(
            passed=True,
            guardrail=GuardrailType.LANGUAGE,
            cleaned_input=text,
        )
    try:
        from langdetect import DetectorFactory, LangDetectException, detect

        DetectorFactory.seed = 0
        language = detect(text)
    except (ImportError, LangDetectException):
        return GuardrailResult(
            passed=True,
            guardrail=GuardrailType.LANGUAGE,
            cleaned_input=text,
        )

    if language in SUPPORTED_LANGUAGES:
        return GuardrailResult(
            passed=True,
            guardrail=GuardrailType.LANGUAGE,
            cleaned_input=text,
        )
    return GuardrailResult(
        passed=False,
        guardrail=GuardrailType.LANGUAGE,
        reason=f"Unsupported language detected: {language}",
    )


class GuardrailOrchestrator:
    """Orchestrates all guardrail checks sequentially."""

    def __init__(self):
        self.checks = [
            detect_pii,
            detect_injection,
            detect_nsfw,
            clean_unsafe_chars,
            detect_language,
        ]

    async def run_all(self, text: str) -> List[GuardrailResult]:
        """Run all guardrail checks on input text."""
        results = []
        current_text = text

        for check in self.checks:
            result = check(current_text)
            results.append(result)

            # If check provides cleaned input, use it for subsequent checks
            if result.cleaned_input is not None:
                current_text = result.cleaned_input

            # Stop on first failure (except unsafe_chars and language which clean/transform)
            if not result.passed and result.guardrail not in (GuardrailType.UNSAFE_CHARS, GuardrailType.LANGUAGE):
                logger.warning(f"Guardrail {result.guardrail.value} failed: {result.reason}")
                break

        return results

    def get_first_failure(self, results: List[GuardrailResult]) -> Optional[GuardrailResult]:
        """Get the first failed guardrail result."""
        for result in results:
            if not result.passed:
                return result
        return None

    def get_cleaned_text(self, results: List[GuardrailResult]) -> str:
        """Get the final cleaned text after all guardrails."""
        for result in reversed(results):
            if result.cleaned_input is not None:
                return result.cleaned_input
        return results[0].cleaned_input if results and results[0].cleaned_input else ""


# Convenience function
async def run_guardrails(text: str) -> tuple[bool, Optional[str], str]:
    """
    Run all guardrails on input text.
    Returns: (passed, refusal_reason, cleaned_text)
    """
    orchestrator = GuardrailOrchestrator()
    results = await orchestrator.run_all(text)

    failure = orchestrator.get_first_failure(results)
    cleaned = orchestrator.get_cleaned_text(results)

    if failure:
        return False, failure.reason, cleaned

    return True, None, cleaned