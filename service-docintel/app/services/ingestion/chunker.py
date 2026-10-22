"""Page-based chunker for document ingestion."""
import logging
from typing import List, Optional
from dataclasses import dataclass
from uuid import uuid4

from app.services.ingestion.parser import ParsedPage

logger = logging.getLogger(__name__)


@dataclass
class Chunk:
    chunk_id: str
    filename: str
    file_id: str
    page: int
    content: str
    category: str
    company: str
    metadata: dict[str, str | int | float]
    embedding: Optional[List[float]] = None


def chunk_page_content(
    parsed_page: ParsedPage,
    filename: str,
    file_id: str,
    chunk_size_kb: int = 2,  # in KB
    chunk_overlap_kb: int = 0,  # in KB
) -> List[Chunk]:
    """
    Chunk a single page's content based on configured size and overlap.
    Since we chunk by page, each page becomes one chunk (or multiple if very large).
    """
    content = parsed_page.content
    page_num = parsed_page.page_number
    page_type = parsed_page.page_type.value

    # Convert KB to characters (approximate: 1 char ≈ 1 byte for ASCII, ~2 for UTF-8)
    chunk_size_chars = chunk_size_kb * 1000
    chunk_overlap_chars = chunk_overlap_kb * 1000

    # For page-based chunking, if content fits in chunk_size, keep as one chunk
    if len(content) <= chunk_size_chars:
        return [Chunk(
            chunk_id=str(uuid4()),
            filename=filename,
            file_id=file_id,
            page=page_num,
            content=content,
            category=page_type,
            company="",  # Will be filled from document metadata if available
            metadata=dict(parsed_page.metadata),
        )]

    # Otherwise, split with overlap
    chunks = []
    start = 0
    chunk_num = 0

    while start < len(content):
        end = min(start + chunk_size_chars, len(content))

        # Try to break at sentence boundary
        if end < len(content):
            # Look for sentence ending within the last 10% of chunk
            search_start = max(start + int(chunk_size_chars * 0.9), start)
            for i in range(end - 1, search_start - 1, -1):
                if content[i] in '.!?':
                    end = i + 1
                    break

        chunk_content = content[start:end].strip()
        if chunk_content:
            chunks.append(Chunk(
                chunk_id=str(uuid4()),
                filename=filename,
                file_id=file_id,
                page=page_num,
                content=chunk_content,
                category=page_type,
                company="",
                metadata={
                    **parsed_page.metadata,
                    "chunk_index": chunk_num,
                    "total_chunks": -1,  # Will update after loop
                },
            ))
            chunk_num += 1

        # Move start with overlap
        start = end - chunk_overlap_chars if end < len(content) else len(content)
        if start < 0:
            start = 0

    # Update total_chunks in metadata
    for chunk in chunks:
        chunk.metadata["total_chunks"] = len(chunks)

    return chunks


def chunk_document(
    parsed_pages: List[ParsedPage],
    filename: str,
    file_id: str,
    chunk_size_kb: int = 2,
    chunk_overlap_kb: int = 0,
) -> List[Chunk]:
    """Chunk all pages of a document."""
    all_chunks = []

    for parsed_page in parsed_pages:
        page_chunks = chunk_page_content(
            parsed_page,
            filename,
            file_id,
            chunk_size_kb,
            chunk_overlap_kb,
        )
        all_chunks.extend(page_chunks)

    logger.info(f"Created {len(all_chunks)} chunks from {len(parsed_pages)} pages")
    return all_chunks