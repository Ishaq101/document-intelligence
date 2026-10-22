"""One process-wide OpenAI client shared by every model call.

The Langfuse OpenAI integration instruments the `AsyncOpenAI` class, so every call made
through this client inherits the active chat trace. A single client also keeps the
underlying HTTP connection pool bounded: creating one per request leaks sockets.
"""

import logging

from langfuse.openai import AsyncOpenAI

from app.config import settings

logger = logging.getLogger(__name__)

_client: AsyncOpenAI | None = None


def get_openai_client() -> AsyncOpenAI:
    """Return the shared client, creating it on first use."""
    global _client

    if _client is None:
        _client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    return _client


async def close_openai_client() -> None:
    """Close the shared client so its connection pool is released."""
    global _client

    client = _client
    _client = None
    if client is None:
        return
    try:
        await client.close()
    except Exception:
        logger.warning("OpenAI client close failed", exc_info=True)
