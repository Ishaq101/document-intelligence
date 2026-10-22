import asyncpg
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional
from uuid import UUID
import logging

from app.config import settings

logger = logging.getLogger(__name__)
SCHEMA = settings.POSTGRES_SCHEMA
DOCUMENTS_TABLE = f'"{SCHEMA}"."documents"'
CHUNKS_TABLE = f'"{SCHEMA}"."chunks"'
CHAT_SESSIONS_TABLE = f'"{SCHEMA}"."chat_sessions"'
MESSAGES_TABLE = f'"{SCHEMA}"."messages"'
ADMIN_CONFIG_TABLE = f'"{SCHEMA}"."admin_config"'
DOCUMENT_CATEGORIES_TABLE = f'"{SCHEMA}"."document_categories"'


class PostgresPool:
    _pool: Optional[asyncpg.Pool] = None

    @staticmethod
    async def _set_search_path(connection: asyncpg.Connection) -> None:
        """Apply configured schema to every newly opened pool connection."""
        await connection.execute(
            "SELECT set_config('search_path', $1, false)",
            settings.POSTGRES_SCHEMA,
        )

    @classmethod
    async def initialize(cls) -> None:
        if cls._pool is None:
            cls._pool = await asyncpg.create_pool(
                dsn=settings.POSTGRES_CONNSTRING,
                min_size=1,
                max_size=settings.POSTGRES_POOL_SIZE,
                max_queries=50000,
                max_inactive_connection_lifetime=300,
                command_timeout=60,
                statement_cache_size=0,
                init=cls._set_search_path,
            )
            logger.info("PostgreSQL connection pool initialized")

    @classmethod
    async def close(cls) -> None:
        if cls._pool:
            await cls._pool.close()
            cls._pool = None
            logger.info("PostgreSQL connection pool closed")

    @classmethod
    async def get_pool(cls) -> asyncpg.Pool:
        """Return shared connection pool, initializing it once."""
        if cls._pool is None:
            await cls.initialize()
        return cls._pool

    @classmethod
    @asynccontextmanager
    async def acquire(cls) -> AsyncGenerator[asyncpg.Connection, None]:
        """Borrow and reliably release one connection from shared pool."""
        pool = await cls.get_pool()
        async with pool.acquire() as conn:
            yield conn

    @classmethod
    async def fetch(cls, query: str, *args) -> list:
        async with cls.acquire() as conn:
            return await conn.fetch(query, *args)

    @classmethod
    async def fetchrow(cls, query: str, *args) -> Optional[asyncpg.Record]:
        async with cls.acquire() as conn:
            return await conn.fetchrow(query, *args)

    @classmethod
    async def fetchval(cls, query: str, *args):
        async with cls.acquire() as conn:
            return await conn.fetchval(query, *args)

    @classmethod
    async def execute(cls, query: str, *args) -> str:
        async with cls.acquire() as conn:
            return await conn.execute(query, *args)

    @classmethod
    async def executemany(cls, query: str, args: list) -> None:
        async with cls.acquire() as conn:
            await conn.executemany(query, args)


async def init_db() -> None:
    """Initialize database tables"""
    await PostgresPool.initialize()

    async with PostgresPool.acquire() as conn:
        # documents table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                file_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id UUID NOT NULL,
                filename VARCHAR(255) NOT NULL,
                status VARCHAR(20) NOT NULL DEFAULT 'pending',
                page_count INTEGER NOT NULL DEFAULT 0,
                file_size_bytes BIGINT NOT NULL,
                category VARCHAR(100),
                upload_timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                processed_timestamp TIMESTAMP WITH TIME ZONE,
                error_message TEXT,
                CONSTRAINT valid_status CHECK (status IN ('pending', 'processing', 'completed', 'failed')),
                CONSTRAINT unique_user_filename UNIQUE (user_id, filename)
            )
        """)
        await conn.execute("ALTER TABLE documents ADD COLUMN IF NOT EXISTS category VARCHAR(100)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_documents_user_id ON documents(user_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(status)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_documents_filename ON documents(filename)")

        # chunks table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS chunks (
                chunk_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                file_id UUID NOT NULL REFERENCES documents(file_id) ON DELETE CASCADE,
                filename VARCHAR(255) NOT NULL,
                page INTEGER NOT NULL,
                category VARCHAR(100),
                company VARCHAR(100),
                content TEXT NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
        """)
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_file_id ON chunks(file_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_filename ON chunks(filename)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_page ON chunks(page)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_category ON chunks(category)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_company ON chunks(company)")
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_chunks_content_fts
            ON chunks USING GIN (to_tsvector('english', content))
        """)

        # chat_sessions table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS chat_sessions (
                session_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id UUID NOT NULL,
                trace_id VARCHAR(100),
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
        """)
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_chat_sessions_user_id ON chat_sessions(user_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_chat_sessions_trace_id ON chat_sessions(trace_id)")

        # messages table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                message_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                session_id UUID NOT NULL REFERENCES chat_sessions(session_id) ON DELETE CASCADE,
                role VARCHAR(20) NOT NULL,
                content TEXT NOT NULL,
                citations JSONB,
                runtime_ms INTEGER,
                timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                CONSTRAINT valid_role CHECK (role IN ('user', 'assistant'))
            )
        """)
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_messages_session_id ON messages(session_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_messages_timestamp ON messages(timestamp)")

        # admin_config table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS admin_config (
                id INTEGER PRIMARY KEY DEFAULT 1,
                chunk_size INTEGER NOT NULL DEFAULT 1,
                chunk_overlap INTEGER NOT NULL DEFAULT 0,
                retrieval_method VARCHAR(20) NOT NULL DEFAULT 'hybrid_rrf',
                top_k INTEGER NOT NULL DEFAULT 5,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                CONSTRAINT single_row CHECK (id = 1),
                CONSTRAINT valid_retrieval_method CHECK (retrieval_method IN ('bm25', 'vector', 'hybrid_rrf'))
            )
        """)
        await conn.execute("INSERT INTO admin_config (id) VALUES (1) ON CONFLICT DO NOTHING")

        # Categories are administered before document ingestion.
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS document_categories (
                category_id SERIAL PRIMARY KEY,
                name VARCHAR(100) NOT NULL UNIQUE,
                description TEXT NOT NULL
            )
        """)
        await conn.execute(
            "ALTER TABLE document_categories ADD COLUMN IF NOT EXISTS description TEXT"
        )
        await conn.execute(
            "UPDATE document_categories SET description = name WHERE description IS NULL"
        )
        await conn.execute(
            "ALTER TABLE document_categories ALTER COLUMN description SET NOT NULL"
        )

        # eval_runs table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS eval_runs (
                run_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                test_case_id VARCHAR(50) NOT NULL,
                category VARCHAR(50) NOT NULL,
                question TEXT NOT NULL,
                predicted_answer TEXT,
                expected_answer TEXT,
                passed BOOLEAN NOT NULL,
                runtime_ms INTEGER,
                citations JSONB,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
        """)
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_eval_runs_test_case ON eval_runs(test_case_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_eval_runs_created_at ON eval_runs(created_at)")

    logger.info("Database tables initialized")


async def get_admin_config() -> dict:
    """Get current admin configuration from configured schema."""
    row = await PostgresPool.fetchrow(f"SELECT * FROM {ADMIN_CONFIG_TABLE} WHERE id = 1")
    return dict(row) if row else {}


async def category_exists(name: str) -> bool:
    """Return whether an admin-defined category exists in configured schema."""
    return bool(
        await PostgresPool.fetchval(
            f"SELECT EXISTS(SELECT 1 FROM {DOCUMENT_CATEGORIES_TABLE} WHERE name = $1)",
            name,
        )
    )


async def create_category(name: str, description: str) -> dict:
    """Create one unique category in configured schema."""
    row = await PostgresPool.fetchrow(
        f"""
        INSERT INTO {DOCUMENT_CATEGORIES_TABLE} (name, description)
        VALUES ($1, $2)
        RETURNING category_id, name, description
        """,
        name,
        description,
    )
    return dict(row)


async def list_categories() -> list[dict]:
    """List categories available during ingestion and retrieval routing."""
    rows = await PostgresPool.fetch(
        f"SELECT category_id, name, description FROM {DOCUMENT_CATEGORIES_TABLE} ORDER BY name"
    )
    return [dict(row) for row in rows]


async def update_admin_config(
    chunk_size: Optional[int] = None,
    chunk_overlap: Optional[int] = None,
    retrieval_method: Optional[str] = None,
    top_k: Optional[int] = None,
) -> dict:
    """Update admin configuration"""
    updates = []
    params = []
    param_idx = 1

    if chunk_size is not None:
        updates.append(f"chunk_size = ${param_idx}")
        params.append(chunk_size)
        param_idx += 1
    if chunk_overlap is not None:
        updates.append(f"chunk_overlap = ${param_idx}")
        params.append(chunk_overlap)
        param_idx += 1
    if retrieval_method is not None:
        updates.append(f"retrieval_method = ${param_idx}")
        params.append(retrieval_method)
        param_idx += 1
    if top_k is not None:
        updates.append(f"top_k = ${param_idx}")
        params.append(top_k)
        param_idx += 1

    if not updates:
        return await get_admin_config()

    updates.append("updated_at = NOW()")
    query = f"UPDATE {ADMIN_CONFIG_TABLE} SET {', '.join(updates)} WHERE id = 1"
    await PostgresPool.execute(query, *params)
    return await get_admin_config()


# Document operations

async def create_document(
    filename: str,
    file_size_bytes: int,
    user_id: UUID,
    category: Optional[str] = None,
) -> dict:
    """Create a new document record"""
    row = await PostgresPool.fetchrow(
        f"""
        INSERT INTO {DOCUMENTS_TABLE} (filename, file_size_bytes, user_id, status, category)
        VALUES ($1, $2, $3, 'pending', $4)
        RETURNING file_id, filename, file_size_bytes, user_id, status, page_count, category, upload_timestamp, processed_timestamp, error_message
        """,
        filename,
        file_size_bytes,
        user_id,
        category,
    )
    return dict(row)


async def get_document(file_id: UUID, user_id: UUID) -> Optional[dict]:
    """Get a document by ID and user"""
    row = await PostgresPool.fetchrow(
        f"""
        SELECT file_id, filename, file_size_bytes, user_id, status, page_count, category, upload_timestamp, processed_timestamp, error_message
        FROM {DOCUMENTS_TABLE}
        WHERE file_id = $1 AND user_id = $2
        """,
        file_id,
        user_id,
    )
    return dict(row) if row else None


async def list_documents(
    user_id: UUID,
    status: str = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list, int]:
    """List documents with optional status filter"""
    where_clause = "WHERE user_id = $1"
    params = [user_id]
    param_idx = 2

    if status:
        where_clause += f" AND status = ${param_idx}"
        params.append(status)
        param_idx += 1

    # Get total count
    count_query = f"SELECT COUNT(*) FROM {DOCUMENTS_TABLE} {where_clause}"
    total = await PostgresPool.fetchval(count_query, *params)

    # Get documents
    params.extend([limit, offset])
    query = f"""
        SELECT file_id, filename, file_size_bytes, user_id, status, page_count, category, upload_timestamp, processed_timestamp, error_message
        FROM {DOCUMENTS_TABLE}
        {where_clause}
        ORDER BY upload_timestamp DESC
        LIMIT ${param_idx} OFFSET ${param_idx + 1}
    """
    rows = await PostgresPool.fetch(query, *params)
    return [dict(row) for row in rows], total


async def update_document_status(
    file_id: UUID,
    status: str,
    page_count: Optional[int] = None,
    error_message: Optional[str] = None,
    user_id: Optional[UUID] = None,
) -> bool:
    """Update document status."""
    status_value = getattr(status, "value", status)
    updates = ["status = $2"]
    params = [file_id, status_value]
    param_idx = 3

    if page_count is not None:
        updates.append(f"page_count = ${param_idx}")
        params.append(page_count)
        param_idx += 1
    if error_message is not None:
        updates.append(f"error_message = ${param_idx}")
        params.append(error_message)
        param_idx += 1
    if status_value == "completed":
        updates.append("processed_timestamp = NOW()")
        updates.append("error_message = NULL")

    if user_id:
        query = f"UPDATE {DOCUMENTS_TABLE} SET {', '.join(updates)} WHERE file_id = $1 AND user_id = ${param_idx}"
        params.append(user_id)
    else:
        query = f"UPDATE {DOCUMENTS_TABLE} SET {', '.join(updates)} WHERE file_id = $1"

    result = await PostgresPool.execute(query, *params)
    return result != "UPDATE 0"


async def delete_document(file_id: UUID, user_id: UUID) -> bool:
    """Delete a document and its chunks (cascades to chunks)."""
    result = await PostgresPool.execute(
        f"DELETE FROM {DOCUMENTS_TABLE} WHERE file_id = $1 AND user_id = $2",
        file_id,
        user_id,
    )
    return result != "DELETE 0"


async def list_document_ids(user_id: UUID) -> list[UUID]:
    """List all document IDs belonging to one user."""
    rows = await PostgresPool.fetch(
        f"SELECT file_id FROM {DOCUMENTS_TABLE} WHERE user_id = $1", user_id
    )
    return [row["file_id"] for row in rows]


async def delete_all_documents(user_id: UUID) -> int:
    """Delete all documents and cascaded chunks for one user."""
    result = await PostgresPool.execute(
        f"DELETE FROM {DOCUMENTS_TABLE} WHERE user_id = $1", user_id
    )
    return int(result.removeprefix("DELETE "))


# Chunk operations

async def insert_chunks(chunks: list) -> int:
    """Insert multiple chunks into PostgreSQL"""
    if not chunks:
        return 0

    # Prepare data for bulk insert
    data = []
    for chunk in chunks:
        data.append((
            chunk.chunk_id,
            chunk.file_id,
            chunk.filename,
            chunk.page,
            chunk.category,
            chunk.company,
            chunk.content,
        ))

    await PostgresPool.executemany(
        f"""
        INSERT INTO {CHUNKS_TABLE} (chunk_id, file_id, filename, page, category, company, content)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        """,
        data,
    )

    return len(data)


async def get_document_chunks(
    file_id: UUID,
    limit: int = 50,
    offset: int = 0,
) -> list:
    """Get chunks for a specific document"""
    rows = await PostgresPool.fetch(
        f"""
        SELECT chunk_id, file_id, filename, page, category, company, content, created_at
        FROM {CHUNKS_TABLE}
        WHERE file_id = $1
        ORDER BY page, chunk_id
        LIMIT $2 OFFSET $3
        """,
        file_id,
        limit,
        offset,
    )
    return [dict(row) for row in rows]


# Chat session operations

async def create_chat_session(user_id: UUID, trace_id: str = None) -> dict:
    """Create a new chat session in configured schema."""
    row = await PostgresPool.fetchrow(
        f"""
        INSERT INTO {CHAT_SESSIONS_TABLE} (user_id, trace_id)
        VALUES ($1, $2)
        RETURNING session_id, user_id, trace_id, created_at, updated_at
        """,
        user_id,
        trace_id,
    )
    return dict(row)


async def get_chat_session(session_id: UUID, user_id: UUID) -> Optional[dict]:
    """Get a chat session by ID from configured schema."""
    row = await PostgresPool.fetchrow(
        f"""
        SELECT session_id, user_id, trace_id, created_at, updated_at
        FROM {CHAT_SESSIONS_TABLE}
        WHERE session_id = $1 AND user_id = $2
        """,
        session_id,
        user_id,
    )
    return dict(row) if row else None


async def list_chat_sessions(
    user_id: UUID,
    limit: int = 50,
    offset: int = 0,
) -> list:
    """List chat sessions from configured schema."""
    rows = await PostgresPool.fetch(
        f"""
        SELECT session_id, user_id, trace_id, created_at, updated_at
        FROM {CHAT_SESSIONS_TABLE}
        WHERE user_id = $1
        ORDER BY updated_at DESC
        LIMIT $2 OFFSET $3
        """,
        user_id,
        limit,
        offset,
    )
    return [dict(row) for row in rows]


async def add_message(
    session_id: UUID,
    role: str,
    content: str,
    citations: list = None,
    runtime_ms: int = None,
) -> dict:
    """Add a message to a configured-schema chat session."""
    import json

    citations_json = json.dumps(citations) if citations else None
    row = await PostgresPool.fetchrow(
        f"""
        INSERT INTO {MESSAGES_TABLE} (session_id, role, content, citations, runtime_ms)
        VALUES ($1, $2, $3, $4, $5)
        RETURNING message_id, session_id, role, content, citations, runtime_ms, timestamp
        """,
        session_id,
        role,
        content,
        citations_json,
        runtime_ms,
    )
    await PostgresPool.execute(
        f"UPDATE {CHAT_SESSIONS_TABLE} SET updated_at = NOW() WHERE session_id = $1",
        session_id,
    )
    return dict(row)


async def get_session_messages(session_id: UUID) -> list:
    """Get all messages for a configured-schema chat session."""
    rows = await PostgresPool.fetch(
        f"""
        SELECT message_id, session_id, role, content, citations, runtime_ms, timestamp
        FROM {MESSAGES_TABLE}
        WHERE session_id = $1
        ORDER BY timestamp
        """,
        session_id,
    )
    return [dict(row) for row in rows]