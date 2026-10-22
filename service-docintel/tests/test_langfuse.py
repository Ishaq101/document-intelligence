"""Regression tests for the best-effort Langfuse adapter.

Everything here is offline: the SDK client is replaced by a recorder, so no network
call, no OpenTelemetry provider, and no database are involved.
"""

from __future__ import annotations

import ast
import asyncio
from collections.abc import Generator, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Literal, cast

import pytest

from app.services.observability import langfuse as lf
from app.services.observability.langfuse import (
    LangfuseContext,
    TimedSpan,
    TraceData,
    _mask_otel_spans,
    _safe_metadata,
    initialize_langfuse,
    shutdown_langfuse,
)

SECRET_QUESTION = "CONFIDENTIAL salary table for employee 88213"
SECRET_ANSWER = "CONFIDENTIAL ANSWER TEXT"


class FakeObservation:
    """Records what the adapter would have sent to Langfuse."""

    def __init__(self, *, name: str, as_type: str, metadata: dict[str, object] | None) -> None:
        self.name = name
        self.as_type = as_type
        self.metadata = metadata or {}
        self.updates: list[dict[str, object]] = []
        self.end_calls = 0
        self.update_failure: Exception | None = None

    def update(self, **kwargs: object) -> FakeObservation:
        if self.update_failure is not None:
            raise self.update_failure
        self.updates.append(kwargs)
        return self

    def end(self) -> FakeObservation:
        self.end_calls += 1
        return self


class FakeContext:
    def __init__(self, observation: FakeObservation) -> None:
        self.observation = observation
        self.enter_calls = 0
        self.exit_calls = 0

    def __enter__(self) -> FakeObservation:
        self.enter_calls += 1
        return self.observation

    def __exit__(self, *exc_info: object) -> Literal[False]:
        self.exit_calls += 1
        return False


class FakeClient:
    """Stand-in for `langfuse.Langfuse` with only the used surface."""

    def __init__(self) -> None:
        self.observations: list[FakeObservation] = []
        self.contexts: list[FakeContext] = []
        self.call_kwargs: list[dict[str, object]] = []
        self.shutdown_calls = 0
        self.auth_ok = True
        self.auth_calls = 0

    def start_as_current_observation(self, **kwargs: object) -> FakeContext:
        self.call_kwargs.append(dict(kwargs))
        raw_metadata = kwargs.get("metadata")
        observation = FakeObservation(
            name=str(kwargs["name"]),
            as_type=str(kwargs["as_type"]),
            metadata=cast(dict[str, object], raw_metadata)
            if isinstance(raw_metadata, dict)
            else None,
        )
        self.observations.append(observation)
        context = FakeContext(observation)
        self.contexts.append(context)
        return context

    def auth_check(self) -> bool:
        self.auth_calls += 1
        return self.auth_ok

    def shutdown(self) -> None:
        self.shutdown_calls += 1


@pytest.fixture(autouse=True)
def reset_module_state() -> Iterator[None]:
    """Each test starts from a clean process-wide adapter state."""
    lf._langfuse = None
    lf._telemetry_enabled = False
    yield
    lf._langfuse = None
    lf._telemetry_enabled = False


@pytest.fixture
def fake_client(monkeypatch: pytest.MonkeyPatch) -> FakeClient:
    client = FakeClient()
    monkeypatch.setattr(lf, "_langfuse", client)
    monkeypatch.setattr(lf, "_telemetry_enabled", True)

    @contextmanager
    def fake_propagate_attributes(**kwargs: object) -> Iterator[None]:
        del kwargs
        yield

    monkeypatch.setattr(lf, "propagate_attributes", fake_propagate_attributes)
    return client


@pytest.fixture
def settings_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(lf.settings, "LANGFUSE_PUBLIC_KEY", "pk-lf-test")
    monkeypatch.setattr(lf.settings, "LANGFUSE_SECRET_KEY", "sk-lf-test")
    monkeypatch.setattr(lf.settings, "LANGFUSE_BASE_URL", "https://langfuse.invalid")


# --- initialization ---------------------------------------------------------------


def test_disabled_without_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(lf.settings, "LANGFUSE_PUBLIC_KEY", "")
    monkeypatch.setattr(lf.settings, "LANGFUSE_SECRET_KEY", "")

    def fail_constructor(**kwargs: object) -> FakeClient:
        raise AssertionError("client must not be constructed without credentials")

    monkeypatch.setattr(lf, "Langfuse", fail_constructor)

    assert initialize_langfuse() is False
    assert lf._langfuse is None


def test_initializes_once_and_reuses_client(
    monkeypatch: pytest.MonkeyPatch, settings_keys: None
) -> None:
    client = FakeClient()
    constructed: list[dict[str, object]] = []

    def constructor(**kwargs: object) -> FakeClient:
        constructed.append(dict(kwargs))
        return client

    monkeypatch.setattr(lf, "Langfuse", constructor)

    assert initialize_langfuse() is True
    assert initialize_langfuse() is True
    assert len(constructed) == 1
    assert client.auth_calls == 1
    assert constructed[0]["mask_otel_spans"] is _mask_otel_spans


def test_auth_failure_disables_telemetry_and_releases_client(
    monkeypatch: pytest.MonkeyPatch, settings_keys: None
) -> None:
    client = FakeClient()
    client.auth_ok = False
    monkeypatch.setattr(lf, "Langfuse", lambda **kwargs: client)

    assert initialize_langfuse() is False
    assert lf._langfuse is None
    assert client.shutdown_calls == 1


def test_constructor_failure_is_a_noop(
    monkeypatch: pytest.MonkeyPatch, settings_keys: None
) -> None:
    def constructor(**kwargs: object) -> FakeClient:
        raise RuntimeError("boom")

    monkeypatch.setattr(lf, "Langfuse", constructor)

    assert initialize_langfuse() is False
    assert lf._langfuse is None


def test_telemetry_is_a_noop_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(lf.settings, "LANGFUSE_PUBLIC_KEY", "")
    monkeypatch.setattr(lf.settings, "LANGFUSE_SECRET_KEY", "")

    with LangfuseContext(user_id="u", question=SECRET_QUESTION) as trace:
        with TimedSpan("guardrails") as span:
            assert span is None
        trace.complete(status="completed", answer_length=3)

    assert lf.get_langfuse() is None


# --- trace structure --------------------------------------------------------------


def test_one_root_observation_per_request(fake_client: FakeClient) -> None:
    with LangfuseContext(
        user_id="user-1",
        question=SECRET_QUESTION,
        metadata={"session_id": "session-1", "streaming": False},
    ) as trace:
        trace.complete(status="completed", answer_length=len(SECRET_ANSWER))

    assert len(fake_client.observations) == 1
    root = fake_client.observations[0]
    assert root.name == "chat_request"
    assert root.as_type == "chain"
    assert len(root.updates) == 1
    output = cast(dict[str, object], root.updates[0]["output"])
    assert output["answer_length"] == len(SECRET_ANSWER)
    assert output["status"] == "completed"
    assert isinstance(output["duration_ms"], int)


def test_children_attach_to_the_active_root(fake_client: FakeClient) -> None:
    with LangfuseContext(user_id="user-1", question=SECRET_QUESTION):
        with TimedSpan("guardrails", {"cleaned_length": 10}, as_type="guardrail"):
            pass
        with TimedSpan("intent_classification", {"cleaned_length": 10}):
            pass

    names = [observation.name for observation in fake_client.observations]
    assert names == ["chat_request", "guardrails", "intent_classification"]
    assert fake_client.observations[1].as_type == "guardrail"
    assert fake_client.observations[2].as_type == "span"


def test_spans_are_skipped_without_an_active_trace(fake_client: FakeClient) -> None:
    with TimedSpan("guardrails") as span:
        assert span is None

    assert fake_client.observations == []


def test_trace_id_is_never_taken_from_the_request(fake_client: FakeClient) -> None:
    with LangfuseContext(
        user_id="user-1",
        question=SECRET_QUESTION,
        metadata={"request_id": "req-123", "session_id": "session-1"},
    ):
        pass

    for call in fake_client.call_kwargs:
        assert "trace_context" not in call
        assert "trace_id" not in call


# --- payload privacy --------------------------------------------------------------


def test_metadata_drops_unknown_and_sensitive_keys() -> None:
    payload: dict[str, object] = {
        "session_id": "session-1",
        "question": SECRET_QUESTION,
        "answer": SECRET_ANSWER,
    }
    filtered = _safe_metadata(cast(TraceData, payload))

    assert filtered == {"session_id": "session-1"}


def test_question_and_answer_never_reach_the_client(fake_client: FakeClient) -> None:
    with LangfuseContext(
        user_id="user-1", question=SECRET_QUESTION, metadata={"session_id": "session-1"}
    ) as trace:
        with TimedSpan("generation", {"chunks": 2}) as span:
            assert span is not None
            span.update(output={"duration_ms": 5})
        trace.complete(status="completed", answer_length=len(SECRET_ANSWER))

    serialized = (
        repr(fake_client.call_kwargs)
        + repr([observation.metadata for observation in fake_client.observations])
        + repr([observation.updates for observation in fake_client.observations])
    )

    assert SECRET_QUESTION not in serialized
    assert SECRET_ANSWER not in serialized
    assert "sk-lf-test" not in serialized


def test_root_input_contains_only_the_question_length(fake_client: FakeClient) -> None:
    with LangfuseContext(user_id="user-1", question=SECRET_QUESTION):
        pass

    root_call = fake_client.call_kwargs[0]
    assert root_call["input"] == {"question_length": len(SECRET_QUESTION)}


def test_mask_strips_generation_payloads_only() -> None:
    from langfuse.types import MaskOtelSpansParams, OtelSpanData, OtelSpanIdentifier

    generation_id = OtelSpanIdentifier(trace_id="a" * 32, span_id="b" * 16)
    chain_id = OtelSpanIdentifier(trace_id="a" * 32, span_id="c" * 16)

    def span(span_id: OtelSpanIdentifier, attributes: dict[str, Any]) -> OtelSpanData:
        return OtelSpanData(
            trace_id=span_id.trace_id,
            span_id=span_id.span_id,
            parent_span_id=None,
            name="probe",
            instrumentation_scope_name="langfuse-sdk",
            instrumentation_scope_version=None,
            attributes=attributes,
            resource_attributes={},
        )

    params = MaskOtelSpansParams(
        spans={
            generation_id: span(
                generation_id,
                {
                    "langfuse.observation.type": "generation",
                    "langfuse.observation.input": SECRET_QUESTION,
                    "langfuse.observation.output": SECRET_ANSWER,
                    "langfuse.observation.status_message": "raw provider error",
                    "langfuse.observation.model.name": "gpt-4o-mini",
                },
            ),
            chain_id: span(
                chain_id,
                {
                    "langfuse.observation.type": "chain",
                    "langfuse.observation.output": '{"status": "completed"}',
                },
            ),
        }
    )

    result = _mask_otel_spans(params=params)

    assert result is not None
    assert set(result.span_patches) == {generation_id}
    patch = result.span_patches[generation_id]
    assert patch is not None
    assert set(patch.delete_attributes) == {
        "langfuse.observation.input",
        "langfuse.observation.output",
        "langfuse.observation.status_message",
    }
    assert dict(patch.set_attributes) == {
        "langfuse.observation.status_message": "generation failed"
    }


def test_mask_returns_none_when_nothing_needs_masking() -> None:
    from langfuse.types import MaskOtelSpansParams, OtelSpanData, OtelSpanIdentifier

    identifier = OtelSpanIdentifier(trace_id="a" * 32, span_id="b" * 16)
    params = MaskOtelSpansParams(
        spans={
            identifier: OtelSpanData(
                trace_id=identifier.trace_id,
                span_id=identifier.span_id,
                parent_span_id=None,
                name="chat_request",
                instrumentation_scope_name="langfuse-sdk",
                instrumentation_scope_version=None,
                attributes={"langfuse.observation.type": "chain"},
                resource_attributes={},
            )
        }
    )

    assert _mask_otel_spans(params=params) is None


# --- lifecycle and failure isolation ----------------------------------------------


def test_exception_marks_the_root_as_failed_and_propagates(fake_client: FakeClient) -> None:
    with pytest.raises(RuntimeError):
        with LangfuseContext(user_id="user-1", question=SECRET_QUESTION):
            raise RuntimeError("business failure")

    root = fake_client.observations[0]
    assert root.updates == [{"level": "ERROR", "status_message": "chat request failed"}]
    assert fake_client.contexts[0].exit_calls == 1


def test_generator_close_is_not_recorded_as_an_error(fake_client: FakeClient) -> None:
    def stream() -> Generator[str, None, None]:
        with LangfuseContext(user_id="user-1", question=SECRET_QUESTION):
            yield "token"

    generator = stream()
    next(generator)
    generator.close()

    root = fake_client.observations[0]
    assert root.updates == []
    assert fake_client.contexts[0].exit_calls == 1


def test_cancellation_is_not_recorded_as_a_failed_request(fake_client: FakeClient) -> None:
    with pytest.raises(asyncio.CancelledError):
        with LangfuseContext(user_id="user-1", question=SECRET_QUESTION):
            raise asyncio.CancelledError

    root = fake_client.observations[0]
    assert root.updates == []
    assert fake_client.contexts[0].exit_calls == 1


def test_contexts_close_exactly_once(fake_client: FakeClient) -> None:
    context = LangfuseContext(user_id="user-1", question=SECRET_QUESTION)
    with context:
        pass
    context.__exit__(None, None, None)

    assert fake_client.contexts[0].exit_calls == 1


def test_telemetry_update_failures_do_not_break_the_request(fake_client: FakeClient) -> None:
    with LangfuseContext(user_id="user-1", question=SECRET_QUESTION) as trace:
        root = fake_client.observations[0]
        root.update_failure = RuntimeError("telemetry down")
        with TimedSpan("guardrails") as span:
            assert span is not None
            cast(FakeObservation, span).update_failure = RuntimeError("telemetry down")
        trace.complete(status="completed", answer_length=1)

    assert fake_client.contexts[0].exit_calls == 1


def test_span_creation_failure_is_swallowed(
    monkeypatch: pytest.MonkeyPatch, fake_client: FakeClient
) -> None:
    def broken(**kwargs: object) -> FakeContext:
        raise RuntimeError("telemetry down")

    monkeypatch.setattr(fake_client, "start_as_current_observation", broken)

    with LangfuseContext(user_id="user-1", question=SECRET_QUESTION) as trace:
        with TimedSpan("guardrails") as span:
            assert span is None
        trace.complete(status="completed", answer_length=1)

    assert lf._telemetry_enabled is True


def test_trace_creation_failure_keeps_chat_usable(
    monkeypatch: pytest.MonkeyPatch, fake_client: FakeClient
) -> None:
    def broken(**kwargs: object) -> FakeContext:
        raise RuntimeError("telemetry down")

    monkeypatch.setattr(fake_client, "start_as_current_observation", broken)

    with LangfuseContext(user_id="user-1", question=SECRET_QUESTION) as trace:
        trace.complete(status="completed", answer_length=1)

    assert lf._telemetry_enabled is True


def test_shutdown_runs_once_and_clears_the_client(fake_client: FakeClient) -> None:
    shutdown_langfuse()
    shutdown_langfuse()

    assert fake_client.shutdown_calls == 1
    assert lf._langfuse is None
    assert lf._telemetry_enabled is False


def test_shutdown_failure_is_swallowed(
    monkeypatch: pytest.MonkeyPatch, fake_client: FakeClient
) -> None:
    def broken() -> None:
        raise RuntimeError("shutdown failed")

    monkeypatch.setattr(fake_client, "shutdown", broken)

    shutdown_langfuse()

    assert lf._langfuse is None


# --- concurrency ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_concurrent_requests_keep_separate_contexts(fake_client: FakeClient) -> None:
    observed: dict[str, list[bool]] = {}

    async def run(user_id: str, delay: float) -> None:
        states: list[bool] = []
        observed[user_id] = states
        with LangfuseContext(user_id=user_id, question=f"question for {user_id}"):
            states.append(lf._current_trace_active.get())
            await asyncio.sleep(delay)
            with TimedSpan(f"generation_{user_id}"):
                await asyncio.sleep(delay)
            states.append(lf._current_trace_active.get())
        states.append(lf._current_trace_active.get())

    await asyncio.gather(run("user-a", 0.01), run("user-b", 0.005))

    assert observed["user-a"] == [True, True, False]
    assert observed["user-b"] == [True, True, False]
    names = [observation.name for observation in fake_client.observations]
    assert sorted(names) == [
        "chat_request",
        "chat_request",
        "generation_user-a",
        "generation_user-b",
    ]


# --- typing rule ------------------------------------------------------------------


def test_observability_module_does_not_use_any() -> None:
    source = Path(lf.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    offenders = [
        node.lineno for node in ast.walk(tree) if isinstance(node, ast.Name) and node.id == "Any"
    ]

    assert offenders == []
