"""Supabase S3-compatible storage for source PDFs."""
import asyncio
from pathlib import Path
from uuid import UUID

import boto3
from botocore.client import BaseClient
from botocore.exceptions import ClientError

from app.config import settings


class ObjectStorage:
    """Persist original PDFs outside API process filesystem."""

    @staticmethod
    def _key(file_id: UUID) -> str:
        return f"documents/{file_id}.pdf"

    @staticmethod
    def _client() -> BaseClient:
        return boto3.client(
            "s3",
            endpoint_url=settings.SUPABASE_S3_ENDPOINT,
            region_name=settings.SUPABASE_S3_REGION,
            aws_access_key_id=settings.SUPABASE_S3_ACCESS_KEY_ID,
            aws_secret_access_key=settings.SUPABASE_S3_SECRET_KEY,
        )

    @classmethod
    async def upload_pdf(cls, file_id: UUID, content: bytes) -> None:
        await asyncio.to_thread(
            cls._client().put_object,
            Bucket=settings.SUPABASE_S3_BUCKET_NAME,
            Key=cls._key(file_id),
            Body=content,
            ContentType="application/pdf",
        )

    @classmethod
    async def download_pdf(cls, file_id: UUID, destination: Path) -> bool:
        try:
            await asyncio.to_thread(
                cls._client().download_file,
                settings.SUPABASE_S3_BUCKET_NAME,
                cls._key(file_id),
                str(destination),
            )
        except ClientError as error:
            error_code = error.response["Error"].get("Code")
            if error_code in {"404", "NoSuchKey", "NoSuchBucket"}:
                return False
            raise
        return True

    @classmethod
    async def delete_pdf(cls, file_id: UUID) -> None:
        await asyncio.to_thread(
            cls._client().delete_object,
            Bucket=settings.SUPABASE_S3_BUCKET_NAME,
            Key=cls._key(file_id),
        )
