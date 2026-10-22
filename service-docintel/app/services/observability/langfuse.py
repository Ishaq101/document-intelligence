"""Best-effort Langfuse tracing for chat requests."""

from __future__ import annotations

import asyncio
import logging
import time
from contextlib import AbstractContextManager
from contextvars import ContextVar, Token
from typing import Literal, Protocol, TypeAlias, TypedDict, cast

from langfuse import Langfuse, propagate_attributes
from langfuse.types import (
    MaskOtelSpansParams,
    MaskOtelSpansResult,
    OtelSpanIdentifier,
    OtelSpanPatch,
)

from app.config import settings

logger = logging.getLogger(__name__)


ObservationType: TypeAlias = Literal[
    "span", "agent", "tool", "chain", "retriever", "evaluator", "guardrail"
]

# Generation and embedding spans are created by the official OpenAI integration, which
# captures the raw prompt and completion. Those payloads are removed at export time so
# document content never leaves the process, while model, usage, and latency survive.
_REDACTED_OBSERVATION_TYPES = frozenset({"generation", "embedding"})
_REDACTED_ATTRIBUTES = (
    "langfuse.observation.input",
    "langfuse.observation.output",
    "langfuse.observation.status_message",
)
_OBSERVATION_TYPE_ATTRIBUTE = "langfuse.observation.type"


class TraceData(TypedDict, total=False):
    answer_length: int
    chunks: int
    chunks_found: int
    cleaned_length: int
    duration_ms: int
    evidence_status: str
    passed: bool
    request_id: str
    result_type: str
    session_id: str
    status: str
    streaming: bool
    task_type: str


class Observation(Protocol):
    """Minimal current Langfuse observation contract used by this adapter."""

    def update(
        self,
        *,
        output: TraceData | None = None,
        metadata: TraceData | None = None,
        level: str | None = None,
        status_message: str | None = None,
    ) -> Observation:
        """Update an observation without exposing business payloads."""

    def end(self) -> Observation:
        """Close this observation."""


_SAFE_METADATA_KEYS = frozenset(TraceData.__annotations__)
_current_trace_active: ContextVar[bool] = ContextVar("_current_trace_active", default=False)
_langfuse: Langfuse | None = None
_telemetry_enabled = False


def _is_client_disconnect(exc_value: object) -> bool:
    """A closed SSE generator or a cancelled task is a disconnect, not a failed request."""
    return isinstance(exc_value, (GeneratorExit, asyncio.CancelledError))


def _mask_otel_spans(*, params: MaskOtelSpansParams) -> MaskOtelSpansResult | None:
    """Strip prompt and completion payloads from every generation before export.

    The OpenAI integration records messages and completions verbatim. Document content,
    questions, and answers must not leave the process, so only the payload attributes are
    removed; model, token usage, latency, and error level are kept.
    """
    patches: dict[OtelSpanIdentifier, OtelSpanPatch] = {}
    for identifier, span in params.spans.items():
        attributes = span.attributes
        observation_type = attributes.get(_OBSERVATION_TYPE_ATTRIBUTE)
        if observation_type not in _REDACTED_OBSERVATION_TYPES:
            continue
        replacements: dict[str, str] = {}
        if "langfuse.observation.status_message" in attributes:
            replacements["langfuse.observation.status_message"] = "generation failed"
        patches[identifier] = OtelSpanPatch(
            delete_attributes=_REDACTED_ATTRIBUTES,
            set_attributes=replacements,
        )
    return MaskOtelSpansResult(span_patches=patches) if patches else None


def _safe_metadata(data: TraceData | None) -> TraceData:
    """Drop any key that is not part of the bounded, non-sensitive allow-list."""
    if data is None:
        return {}
    filtered: dict[str, object] = {
        key: value for key, value in data.items() if key in _SAFE_METADATA_KEYS
    }
    return cast(TraceData, filtered)


def initialize_langfuse() -> bool:
    """Initialize one Langfuse client without making telemetry a service dependency."""
    global _langfuse, _telemetry_enabled

    if _langfuse is not None:
        return _telemetry_enabled
    if not settings.LANGFUSE_PUBLIC_KEY or not settings.LANGFUSE_SECRET_KEY:
        logger.info("Langfuse tracing disabled because credentials are not configured")
        return False

    client: Langfuse | None = None
    try:
        client = Langfuse(
            public_key=settings.LANGFUSE_PUBLIC_KEY,
            secret_key=settings.LANGFUSE_SECRET_KEY,
            base_url=settings.LANGFUSE_BASE_URL,
            tracing_enabled=True,
            mask_otel_spans=_mask_otel_spans,
        )
        if not client.auth_check():
            logger.warning("Langfuse tracing disabled because authentication failed")
            _shutdown_client(client)
            return False
        _langfuse = client
        _telemetry_enabled = True
        return True
    except Exception:
        logger.warning("Langfuse tracing disabled because initialization failed", exc_info=True)
        if client is not None:
            _shutdown_client(client)
        return False


def _shutdown_client(client: Langfuse) -> None:
    """Stop a client that will never be used so its background workers do not linger."""
    try:
        client.shutdown()
    except Exception:
        logger.warning("Langfuse client cleanup failed", exc_info=True)


def get_langfuse() -> Langfuse | None:
    """Return the enabled process client, initializing it lazily when needed."""
    initialize_langfuse()
    return _langfuse if _telemetry_enabled else None


def shutdown_langfuse() -> None:
    """Flush and stop Langfuse background work once during application shutdown."""
    global _langfuse, _telemetry_enabled

    client = _langfuse
    _langfuse = None
    _telemetry_enabled = False
    if client is None:
        return
    try:
        client.shutdown()
    except Exception:
        logger.warning("Langfuse shutdown failed", exc_info=True)


class LangfuseContext:
    """One safe root observation for a chat request."""

    def __init__(
        self,
        *,
        user_id: str,
        question: str,
        metadata: TraceData | None = None,
    ):
        self.user_id = user_id
        self.question_length = len(question)
        self.metadata = _safe_metadata(metadata)
        self._attributes_context: AbstractContextManager[object] | None = None
        self._observation_context: AbstractContextManager[Observation] | None = None
        self._root: Observation | None = None
        self._token: Token[bool] | None = None
        self._started_at = 0.0

    def __enter__(self) -> LangfuseContext:
        client = get_langfuse()
        if client is None:
            return self

        try:
            self._started_at = time.perf_counter()
            self._attributes_context = cast(
                AbstractContextManager[object],
                propagate_attributes(
                    user_id=self.user_id,
                    session_id=self.metadata.get("session_id"),
                    trace_name="chat_request",
                ),
            )
            self._attributes_context.__enter__()
            self._observation_context = cast(
                AbstractContextManager[Observation],
                client.start_as_current_observation(
                    as_type="chain",
                    name="chat_request",
                    input={"question_length": self.question_length},
                    metadata=self.metadata,
                ),
            )
            self._root = self._observation_context.__enter__()
            self._token = _current_trace_active.set(True)
        except Exception:
            logger.warning("Langfuse trace creation failed", exc_info=True)
            self._close_telemetry_contexts()
        return self

    def complete(self, *, status: str, answer_length: int = 0) -> None:
        """Record a bounded chat outcome without storing answer text."""
        if self._root is None:
            return
        try:
            duration_ms = int((time.perf_counter() - self._started_at) * 1000)
            self._root.update(
                output={
                    "answer_length": answer_length,
                    "duration_ms": duration_ms,
                    "status": status,
                }
            )
        except Exception:
            logger.warning("Langfuse trace update failed", exc_info=True)

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> Literal[False]:
        if (
            self._root is not None
            and exc_value is not None
            and not _is_client_disconnect(exc_value)
        ):
            try:
                self._root.update(level="ERROR", status_message="chat request failed")
            except Exception:
                logger.warning("Langfuse error update failed", exc_info=True)
        self._close_telemetry_contexts()
        return False

    def _close_telemetry_contexts(self) -> None:
        if self._token is not None:
            try:
                _current_trace_active.reset(self._token)
            except ValueError:
                # The token belongs to another context when a streaming generator is closed
                # from a different task; the flag is per-context, so nothing leaks.
                logger.debug("Langfuse trace flag could not be restored in this context")
            self._token = None
        if self._observation_context is not None:
            try:
                self._observation_context.__exit__(None, None, None)
            except Exception:
                logger.warning("Langfuse trace close failed", exc_info=True)
            self._observation_context = None
            self._root = None
        if self._attributes_context is not None:
            try:
                self._attributes_context.__exit__(None, None, None)
            except Exception:
                logger.warning("Langfuse attribute context close failed", exc_info=True)
            self._attributes_context = None


class TimedSpan:
    """Nested operation observation with safe duration and error status only."""

    def __init__(
        self,
        name: str,
        metadata: TraceData | None = None,
        as_type: ObservationType = "span",
    ):
        self.name = name
        self.metadata = _safe_metadata(metadata)
        self.as_type = as_type
        self._context: AbstractContextManager[Observation] | None = None
        self._span: Observation | None = None
        self._started_at = 0.0

    def __enter__(self) -> Observation | None:
        if not _current_trace_active.get():
            return None
        client = get_langfuse()
        if client is None:
            return None
        try:
            self._started_at = time.perf_counter()
            self._context = cast(
                AbstractContextManager[Observation],
                client.start_as_current_observation(
                    as_type=self.as_type,
                    name=self.name,
                    metadata=self.metadata,
                ),
            )
            self._span = self._context.__enter__()
            return self._span
        except Exception:
            logger.warning("Langfuse span creation failed", exc_info=True)
            self._close()
            return None

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> Literal[False]:
        if self._span is not None:
            try:
                output: TraceData = {
                    "duration_ms": int((time.perf_counter() - self._started_at) * 1000)
                }
                if exc_value is not None and not _is_client_disconnect(exc_value):
                    self._span.update(
                        output=output,
                        level="ERROR",
                        status_message="operation failed",
                    )
                else:
                    self._span.update(output=output)
            except Exception:
                logger.warning("Langfuse span update failed", exc_info=True)
        self._close()
        return False

    def _close(self) -> None:
        if self._context is not None:
            try:
                self._context.__exit__(None, None, None)
            except Exception:
                logger.warning("Langfuse span close failed", exc_info=True)
            self._context = None
            self._span = None
