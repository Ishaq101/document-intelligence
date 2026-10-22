"""Route PDF pages to text, table, or visual parsers."""

import asyncio
import logging
import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)

_MIN_TEXT_LENGTH = 150
_SCANNED_IMAGE_COVERAGE = 0.60
_VISUAL_IMAGE_COVERAGE = 0.12
_CHART_TERMS = re.compile(
    r"\b(chart|analysis|trend|revenue|quarter|performance|growth|share|market|emissions)\b",
    re.IGNORECASE,
)
_NUMBER_PATTERN = re.compile(r"\b\d+(?:[.,]\d+)?%?\b")


class PageType(StrEnum):
    TEXT = "text"
    TABLE = "table"
    IMAGE = "image"
    CHART = "chart"
    SCANNED = "scanned"


@dataclass(frozen=True)
class PageAnalysis:
    page_number: int
    page_type: PageType
    text_length: int
    image_count: int
    image_coverage: float
    drawing_count: int
    table_count: int


@dataclass
class ParsedPage:
    page_number: int
    page_type: PageType
    content: str
    metadata: dict[str, str | int | float]


def classify_page(
    *,
    page_number: int,
    text: str,
    image_count: int,
    image_coverage: float,
    drawing_count: int,
    table_count: int,
) -> PageAnalysis:
    """Classify one page using content signals only."""
    text_length = len(text.strip())
    has_large_visual = image_count > 0 and image_coverage >= _VISUAL_IMAGE_COVERAGE
    is_scanned = image_count > 0 and image_coverage >= _SCANNED_IMAGE_COVERAGE
    numeric_labels = len(_NUMBER_PATTERN.findall(text))
    is_chart = (
        has_large_visual
        and bool(_CHART_TERMS.search(text))
        and numeric_labels >= 2
        and table_count <= 2
        and text_length < 1_200
    )

    if is_scanned:
        page_type = PageType.SCANNED
    elif is_chart:
        page_type = PageType.CHART
    elif has_large_visual:
        page_type = PageType.IMAGE
    elif table_count > 0:
        page_type = PageType.TABLE
    elif text_length < _MIN_TEXT_LENGTH and image_count > 0:
        page_type = PageType.SCANNED
    else:
        page_type = PageType.TEXT

    return PageAnalysis(
        page_number=page_number,
        page_type=page_type,
        text_length=text_length,
        image_count=image_count,
        image_coverage=image_coverage,
        drawing_count=drawing_count,
        table_count=table_count,
    )


def analyze_document(pdf_path: str) -> list[PageAnalysis]:
    """Read the PDF once and classify every page without filename or page hints."""
    import pymupdf

    analyses: list[PageAnalysis] = []
    with pymupdf.open(pdf_path) as document:
        for page_number, page in enumerate(document, start=1):
            page_area = page.rect.get_area()
            image_rects = [
                rect for image in page.get_images(full=True) for rect in page.get_image_rects(image)
            ]
            image_coverage = (
                min(1.0, sum(rect.get_area() for rect in image_rects) / page_area)
                if page_area
                else 0.0
            )
            try:
                table_count = len(page.find_tables().tables)
            except Exception as error:
                logger.debug("Table detection failed on page %s: %s", page_number, error)
                table_count = 0
            analyses.append(
                classify_page(
                    page_number=page_number,
                    text=page.get_text(),
                    image_count=len(image_rects),
                    image_coverage=image_coverage,
                    drawing_count=len(page.get_drawings()),
                    table_count=table_count,
                )
            )
    return analyses


async def parse_with_pypdf(pdf_path: str, page_num: int) -> str:
    """Extract one text page using pypdf."""
    from pypdf import PdfReader

    reader = PdfReader(pdf_path)
    return reader.pages[page_num - 1].extract_text() or ""


async def parse_with_pdfplumber(pdf_path: str, page_num: int) -> str:
    """Extract one table page as Markdown using pdfplumber."""
    import pdfplumber

    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[page_num - 1]
        tables = page.extract_tables()
        if not tables:
            return page.extract_text() or ""

        result: list[str] = []
        for table in tables:
            if not table:
                continue
            header = table[0]
            result.append("| " + " | ".join(str(cell) if cell else "" for cell in header) + " |")
            result.append("| " + " | ".join("---" for _ in header) + " |")
            for row in table[1:]:
                result.append("| " + " | ".join(str(cell) if cell else "" for cell in row) + " |")
            result.append("")
        return "\n".join(result)


def _parse_visual_pages_sync(pdf_path: str, page_numbers: list[int]) -> dict[int, str]:
    """Parse selected visual pages in one LlamaParse job."""
    from llama_cloud import LlamaCloud

    if not settings.LLAMAPARSE_API_KEY.strip():
        raise RuntimeError("LLAMAPARSE_API_KEY is required for visual pages")

    client = LlamaCloud(api_key=settings.LLAMAPARSE_API_KEY)
    with Path(pdf_path).open("rb") as pdf_file:
        uploaded = client.files.create(file=pdf_file, purpose="parse")

    try:
        response = client.parsing.parse(
            file_id=uploaded.id,
            tier="agentic",
            version="latest",
            expand=["markdown"],
            page_ranges={"target_pages": ",".join(str(page) for page in page_numbers)},
            processing_options={"specialized_chart_parsing": "agentic_plus"},
        )
        if response.markdown is None:
            raise RuntimeError("LlamaParse returned no per-page Markdown")

        expected = set(page_numbers)
        parsed: dict[int, str] = {}
        failed: list[int] = []
        for page in response.markdown.pages:
            if page.page_number not in expected:
                raise RuntimeError(f"LlamaParse returned unexpected page {page.page_number}")
            if not page.success:
                failed.append(page.page_number)
                continue
            content = getattr(page, "markdown", "").strip()
            if not content:
                failed.append(page.page_number)
                continue
            if page.page_number in parsed:
                raise RuntimeError(f"LlamaParse returned duplicate page {page.page_number}")
            parsed[page.page_number] = content

        missing = sorted(expected - parsed.keys())
        if failed or missing:
            affected = sorted(set(failed + missing))
            raise RuntimeError(f"LlamaParse failed to extract visual pages: {affected}")
        return parsed
    finally:
        client.files.delete(uploaded.id)


async def parse_visual_pages(pdf_path: str, page_numbers: list[int]) -> dict[int, str]:
    """Run the synchronous Llama Cloud client outside the event loop."""
    return await asyncio.to_thread(_parse_visual_pages_sync, pdf_path, page_numbers)


def _metadata(analysis: PageAnalysis, actual_parser: str) -> dict[str, str | int | float]:
    return {
        "detected_page_type": analysis.page_type.value,
        "actual_parser": actual_parser,
        "text_length": analysis.text_length,
        "image_count": analysis.image_count,
        "image_coverage": round(analysis.image_coverage, 4),
        "drawing_count": analysis.drawing_count,
        "table_count": analysis.table_count,
    }


async def parse_document(pdf_path: str) -> list[ParsedPage]:
    """Parse all PDF pages, failing if any visual page cannot be extracted."""
    analyses = analyze_document(pdf_path)
    visual_types = {PageType.IMAGE, PageType.CHART, PageType.SCANNED}
    visual_page_numbers = [
        analysis.page_number for analysis in analyses if analysis.page_type in visual_types
    ]
    visual_content = (
        await parse_visual_pages(pdf_path, visual_page_numbers) if visual_page_numbers else {}
    )

    pages: list[ParsedPage] = []
    for analysis in analyses:
        if analysis.page_type in visual_types:
            content = visual_content[analysis.page_number]
            parser_name = "llamaparse"
        elif analysis.page_type == PageType.TABLE:
            content = await parse_with_pdfplumber(pdf_path, analysis.page_number)
            parser_name = "pdfplumber"
        else:
            content = await parse_with_pypdf(pdf_path, analysis.page_number)
            parser_name = "pypdf"

        stripped = content.strip()
        if not stripped:
            raise RuntimeError(f"No content extracted from page {analysis.page_number}")
        pages.append(
            ParsedPage(
                page_number=analysis.page_number,
                page_type=analysis.page_type,
                content=stripped,
                metadata=_metadata(analysis, parser_name),
            )
        )
    return pages
