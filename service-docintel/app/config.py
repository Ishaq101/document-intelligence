from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional
from functools import lru_cache
from pathlib import Path


ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    # App
    APP_NAME: str = "Document Intelligence"
    DEBUG: bool = Field(default=False, validation_alias="DEBUG")
    HOST: str = "0.0.0.0"
    PORT: int = 8010

    # OpenAI
    OPENAI_API_KEY: str = Field(..., validation_alias="OPENAI_API_KEY")
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    EMBEDDING_DIMENSION: int = 1536
    LLM_MODEL: str = "gpt-6-luna"
    LLM_MAX_TOKENS: int = 4096
    LLM_THINKING_EFFORT: str = "medium"

    # LlamaParse
    LLAMAPARSE_API_KEY: str = Field(..., validation_alias="LLAMAPARSE_API_KEY")

    # PaddleOCR (future)
    PADDLE_OCR_API_KEY: Optional[str] = Field(default=None, validation_alias="PADDLE_OCR_API_KEY")

    # PostgreSQL (Neon)
    POSTGRES_CONNSTRING: str = Field(..., validation_alias="POSTGRES_CONNSTRING")
    POSTGRES_SCHEMA: str = Field(
        default="svc_docintel",
        validation_alias="POSTGRES_SCHEMA",
        pattern=r"^[A-Za-z_][A-Za-z0-9_]*$",
    )
    POSTGRES_POOL_SIZE: int = 10
    POSTGRES_MAX_OVERFLOW: int = 20

    # Qdrant Cloud
    QDRANT_API_KEY: str = Field(..., validation_alias="QDRANT_API_KEY")
    QDRANT_ENDPOINT: str = Field(..., validation_alias="QDRANT_ENDPOINT")
    QDRANT_COLLECTION: str = "document_chunks"

    # Supabase Storage (S3-compatible)
    SUPABASE_S3_ENDPOINT: str = Field(..., validation_alias="SUPABASE_S3_ENDPOINT")
    SUPABASE_S3_REGION: str = Field(..., validation_alias="SUPABASE_S3_REGION")
    SUPABASE_S3_ACCESS_KEY_ID: str = Field(..., validation_alias="SUPABASE_S3_ACCESS_KEY_ID")
    SUPABASE_S3_SECRET_KEY: str = Field(..., validation_alias="SUPABASE_S3_SECRET_KEY")
    SUPABASE_S3_BUCKET_NAME: str = Field(..., validation_alias="SUPABASE_S3_BUCKET_NAME")

    # Langfuse
    LANGFUSE_PUBLIC_KEY: str = Field(default="", validation_alias="LANGFUSE_PUBLIC_KEY")
    LANGFUSE_SECRET_KEY: str = Field(default="", validation_alias="LANGFUSE_SECRET_KEY")
    LANGFUSE_BASE_URL: str = Field(
        default="https://us.cloud.langfuse.com", validation_alias="LANGFUSE_BASE_URL"
    )

    # Frontend URL (for CORS)
    FRONTEND_URL: str = Field(default="http://localhost:3010", validation_alias="FRONTEND_URL")

    @property
    def CORS_ORIGINS(self) -> list[str]:
        return [self.FRONTEND_URL]

    class Config:
        env_file = ENV_FILE
        env_file_encoding = "utf-8"
        case_sensitive = True
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()