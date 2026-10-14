"""Unit tests for Universal DocumentReader and IngestDocumentTool."""

from pathlib import Path

import pytest

from nani.tools.document_reader import DocumentReader, IngestDocumentTool


def test_read_local_file(tmp_path: Path):
    f = tmp_path / "sample.txt"
    f.write_text("Hello NANI Sovereign AI\nLine 2 content")

    res = DocumentReader.read_local_file(f)
    assert res["source_type"] == "file"
    assert "Hello NANI" in res["content"]
    assert res["size_chars"] > 0


def test_chunk_content():
    text = "A" * 10000
    chunks = DocumentReader.chunk_content(text, chunk_size=3000, overlap=500)
    assert len(chunks) >= 4
    for ch in chunks:
        assert len(ch) <= 3000


@pytest.mark.asyncio
async def test_ingest_document_tool_local(tmp_path: Path):
    f = tmp_path / "doc.md"
    f.write_text("# Documentation\nDetails about system control.")

    tool = IngestDocumentTool()
    result = await tool.run(source=str(f))

    assert result.success is True
    assert result.data["source_type"] == "file"
    assert "# Documentation" in result.data["content"]


@pytest.mark.asyncio
async def test_ingest_document_tool_rejects_empty():
    tool = IngestDocumentTool()
    result = await tool.run(source="")
    assert result.success is False
    assert "Missing required parameter" in result.error
