"""Unit tests for Phase 2 Web Search & Page Fetching Tools."""

import pytest

from nani.tools.web_search import FetchWebPageTool, WebSearchTool


@pytest.mark.asyncio
async def test_web_search_tool_validation():
    tool = WebSearchTool()
    assert tool.name == "web_search"

    # Missing query
    res = await tool.run(query="")
    assert res.success is False
    assert "Missing required parameter" in res.error

    # Parameter schema validation
    val_err = tool.validate_parameters({})
    assert val_err is not None
    assert "query" in val_err


@pytest.mark.asyncio
async def test_fetch_web_page_tool_validation():
    tool = FetchWebPageTool()
    assert tool.name == "fetch_web_page"

    # Missing URL
    res = await tool.run(url="")
    assert res.success is False
    assert "Missing required parameter" in res.error

    # Invalid URL scheme
    res_bad = await tool.run(url="file:///etc/shadow")
    assert res_bad.success is False
    assert "Invalid URL schema" in res_bad.error

    res_ftp = await tool.run(url="ftp://ftp.example.com")
    assert res_ftp.success is False
    assert "Invalid URL schema" in res_ftp.error
