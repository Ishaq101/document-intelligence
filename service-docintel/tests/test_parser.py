from pathlib import Path
from unittest.mock import AsyncMock

import pymupdf
import pytest

from app.services.ingestion.chunker import chunk_page_content
from app.services.ingestion.parser import (
    PageType,
    ParsedPage,
    analyze_document,
    classify_page,
    parse_document,
)

SAMPLE_PDF = (
    Path(__file__).parents[1]
    / "evals"
    / "sample_documents"
    / "Kirana_Logistics_Annual_Report_2025.pdf"
)


@pytest.mark.parametrize(
    ("signals", "expected"),
    [
        (
            {
                "text": "Normal narrative " * 20,
                "image_count": 0,
                "image_coverage": 0.0,
                "drawing_count": 1,
                "table_count": 0,
            },
            PageType.TEXT,
        ),
        (
            {
                "text": "Column data " * 20,
                "image_count": 0,
                "image_coverage": 0.0,
                "drawing_count": 12,
                "table_count": 1,
            },
            PageType.TABLE,
        ),
        (
            {
                "text": "Illustrated annual report",
                "image_count": 1,
                "image_coverage": 0.3,
                "drawing_count": 1,
                "table_count": 0,
            },
            PageType.IMAGE,
        ),
        (
            {
                "text": "Quarterly revenue analysis Q1 10 Q2 20 Q3 30",
                "image_count": 1,
                "image_coverage": 0.3,
                "drawing_count": 1,
                "table_count": 0,
            },
            PageType.CHART,
        ),
        (
            {
                "text": "Page 1",
                "image_count": 1,
                "image_coverage": 0.8,
                "drawing_count": 1,
                "table_count": 0,
            },
            PageType.SCANNED,
        ),
        (
            {
                "text": "Table with an illustration",
                "image_count": 1,
                "image_coverage": 0.3,
                "drawing_count": 10,
                "table_count": 1,
            },
            PageType.IMAGE,
        ),
    ],
)
def test_classify_page_uses_content_signals(
    signals: dict[str, str | int | float], expected: PageType
) -> None:
    result = classify_page(page_number=99, **signals)
    assert result.page_type == expected


def test_kirana_classification_uses_no_filename_hint(tmp_path: Path) -> None:
    renamed = tmp_path / "unrelated-name.pdf"
    renamed.write_bytes(SAMPLE_PDF.read_bytes())

    original = analyze_document(str(SAMPLE_PDF))
    copied = analyze_document(str(renamed))

    assert [page.page_type for page in copied] == [page.page_type for page in original]
    expected = {
        1: PageType.IMAGE,
        3: PageType.IMAGE,
        4: PageType.TABLE,
        5: PageType.CHART,
        6: PageType.CHART,
        7: PageType.IMAGE,
        8: PageType.TABLE,
        9: PageType.CHART,
        10: PageType.TABLE,
        13: PageType.SCANNED,
    }
    assert {
        page.page_number: page.page_type for page in original if page.page_number in expected
    } == expected


def test_reordered_fixture_classifies_by_content(tmp_path: Path) -> None:
    reordered = tmp_path / "reordered.pdf"
    with pymupdf.open(SAMPLE_PDF) as source, pymupdf.open() as output:
        output.insert_pdf(source, from_page=12, to_page=12)
        output.insert_pdf(source, from_page=4, to_page=4)
        output.save(reordered)

    analyses = analyze_document(str(reordered))
    assert [page.page_type for page in analyses] == [PageType.SCANNED, PageType.CHART]


@pytest.mark.asyncio
async def test_parse_document_batches_visual_pages_and_routes_local_parsers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    analyses = analyze_document(str(SAMPLE_PDF))
    visual_pages = [
        page.page_number
        for page in analyses
        if page.page_type in {PageType.IMAGE, PageType.CHART, PageType.SCANNED}
    ]
    visual_parser = AsyncMock(return_value={page: f"visual page {page}" for page in visual_pages})
    table_parser = AsyncMock(side_effect=lambda _path, page: f"table page {page}")
    text_parser = AsyncMock(side_effect=lambda _path, page: f"text page {page}")
    monkeypatch.setattr("app.services.ingestion.parser.parse_visual_pages", visual_parser)
    monkeypatch.setattr("app.services.ingestion.parser.parse_with_pdfplumber", table_parser)
    monkeypatch.setattr("app.services.ingestion.parser.parse_with_pypdf", text_parser)

    pages = await parse_document(str(SAMPLE_PDF))

    visual_parser.assert_awaited_once_with(str(SAMPLE_PDF), visual_pages)
    assert len(pages) == 13
    for page in pages:
        expected_parser = {
            PageType.IMAGE: "llamaparse",
            PageType.CHART: "llamaparse",
            PageType.SCANNED: "llamaparse",
            PageType.TABLE: "pdfplumber",
            PageType.TEXT: "pypdf",
        }[page.page_type]
        assert page.metadata["actual_parser"] == expected_parser


@pytest.mark.asyncio
async def test_visual_parse_failure_aborts_document(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.services.ingestion.parser.parse_visual_pages",
        AsyncMock(side_effect=RuntimeError("visual parse failed")),
    )
    with pytest.raises(RuntimeError, match="visual parse failed"):
        await parse_document(str(SAMPLE_PDF))


def test_chunk_preserves_parser_metadata() -> None:
    page = ParsedPage(
        page_number=7,
        page_type=PageType.IMAGE,
        content="extracted visual content",
        metadata={"detected_page_type": "image", "actual_parser": "llamaparse"},
    )
    chunks = chunk_page_content(page, "renamed.pdf", "file-id")
    assert chunks[0].page == 7
    assert chunks[0].metadata["detected_page_type"] == "image"
    assert chunks[0].metadata["actual_parser"] == "llamaparse"
