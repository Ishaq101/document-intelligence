import json
import logging
from collections.abc import AsyncGenerator
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.models.agent import ChatRequest, ChatResponse
from app.services.agent.orchestration import AgentOrchestration
from app.services.observability.langfuse import LangfuseContext
from app.services.storage.postgres import (
    add_message,
    create_chat_session,
    get_chat_session,
    get_session_messages,
    list_chat_sessions,
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    x_request_id: str | None = Header(None, alias="X-Request-Id"),
    user_id: UUID = UUID("00000000-0000-0000-0000-000000000001"),  # Seed user
):
    """Chat with the document agent (non-streaming for simple requests)"""
    # Get or create session
    if request.session_id:
        session = await get_chat_session(request.session_id, user_id)
        if not session:
            raise HTTPException(status_code=404, detail="Chat session not found")
        session_id = request.session_id
    else:
        session = await create_chat_session(user_id)
        session_id = session["session_id"]

    # Add user message
    await add_message(session_id, "user", request.question)

    # Run agent orchestration with Langfuse tracing.
    with LangfuseContext(
        user_id=str(user_id),
        question=request.question,
        metadata={
            "request_id": x_request_id[:128] if x_request_id else "",
            "session_id": str(session_id),
            "streaming": False,
        },
    ) as trace:
        orchestration = AgentOrchestration()
        result = await orchestration.generate_answer(request.question, session_id, user_id)
        trace.complete(status="completed", answer_length=len(result.answer.answer))

    return ChatResponse(
        session_id=session_id,
        answer=result.answer.answer,
        citations=result.answer.citations,
        runtime_ms=result.runtime_ms,
    )


@router.post("/stream")
async def chat_stream(
    request: ChatRequest,
    x_request_id: str | None = Header(None, alias="X-Request-Id"),
    user_id: UUID = UUID("00000000-0000-0000-0000-000000000001"),  # Seed user
):
    """Chat with the document agent (SSE streaming)"""
    # Get or create session
    if request.session_id:
        session = await get_chat_session(request.session_id, user_id)
        if not session:
            raise HTTPException(status_code=404, detail="Chat session not found")
        session_id = request.session_id
    else:
        session = await create_chat_session(user_id)
        session_id = session["session_id"]

    # Add user message
    await add_message(session_id, "user", request.question)

    async def event_generator() -> AsyncGenerator[str, None]:
        """Generate SSE events"""
        try:
            with LangfuseContext(
                user_id=str(user_id),
                question=request.question,
                metadata={
                    "request_id": x_request_id[:128] if x_request_id else "",
                    "session_id": str(session_id),
                    "streaming": True,
                },
            ) as trace:
                orchestration = AgentOrchestration()
                answer_length = 0

                # Send session_id first
                yield f"data: {json.dumps({'type': 'session', 'session_id': str(session_id)})}\n\n"

                # Stream the response
                async for chunk in orchestration.generate_answer_stream(
                    request.question, session_id, user_id
                ):
                    if chunk["type"] == "token":
                        answer_length += len(chunk["content"])
                    yield f"data: {json.dumps(chunk)}\n\n"
                trace.complete(status="completed", answer_length=answer_length)

        except Exception as e:
            logger.error(f"Stream error: {e}")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/sessions", response_model=list[dict])
async def list_sessions(
    user_id: UUID = UUID("00000000-0000-0000-0000-000000000001"),  # Seed user
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """List chat sessions for the user"""
    sessions = await list_chat_sessions(user_id, limit=limit, offset=offset)
    return sessions


@router.get("/sessions/{session_id}")
async def get_session(
    session_id: UUID,
    user_id: UUID = UUID("00000000-0000-0000-0000-000000000001"),  # Seed user
):
    """Get a chat session with its messages"""
    session = await get_chat_session(session_id, user_id)
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")

    messages = await get_session_messages(session_id)
    return {
        "session_id": session["session_id"],
        "user_id": session["user_id"],
        "created_at": session["created_at"],
        "updated_at": session["updated_at"],
        "messages": messages,
    }
