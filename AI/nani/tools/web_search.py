"""N.A.N.I. V2 — Structured Web Search & Content Extraction Tools
Enables autonomous web research, real-time knowledge lookup, and document retrieval.
Strictly bounded buffer sizes and timeouts to prevent hanging or memory exhaustion.
"""

import urllib.parse
from typing import Any

import httpx
from bs4 import BeautifulSoup

from nani.core.task import RiskLevel, WorkerCapability
from nani.tools.registry import BaseTool, ToolRegistry
from nani.tools.result import ToolResult

USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 NANI/2.0"
MAX_CONTENT_BYTES = 500_000


class WebSearchTool(BaseTool):
    """Searches the internet for information, technical documentation, and answers."""

    def __init__(self, timeout_seconds: float = 15.0) -> None:
        self.timeout_seconds = timeout_seconds

    @property
    def name(self) -> str:
        return "web_search"

    @property
    def description(self) -> str:
        return "Searches the web for queries, articles, and documentation."

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.LOW

    @property
    def capability(self) -> WorkerCapability:
        return WorkerCapability.RESEARCH

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search terms or question"},
                "max_results": {
                    "type": "integer",
                    "description": "Maximum search results to return",
                    "default": 5,
                },
            },
            "required": ["query"],
        }

    async def run(self, **kwargs: Any) -> ToolResult:
        query = str(kwargs.get("query", "")).strip()
        if not query:
            return ToolResult.fail("Missing required parameter: 'query'")

        max_results = min(max(int(kwargs.get("max_results", 5)), 1), 10)
        encoded_query = urllib.parse.quote_plus(query)
        # Use DuckDuckGo HTML endpoint (zero API key requirement)
        search_url = f"https://html.duckduckgo.com/html/?q={encoded_query}"

        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
        }

        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_seconds, follow_redirects=True
            ) as client:
                resp = await client.get(search_url, headers=headers)

            if resp.status_code != 200:
                return ToolResult.fail(
                    f"Search engine responded with status code {resp.status_code}"
                )

            soup = BeautifulSoup(resp.text, "html.parser")
            results = []

            for result_elem in soup.select(".result"):
                title_elem = result_elem.select_one(".result__title a")
                snippet_elem = result_elem.select_one(".result__snippet")

                if title_elem and title_elem.text:
                    title = title_elem.text.strip()
                    raw_href_val = title_elem.get("href", "")
                    raw_href = str(raw_href_val) if raw_href_val is not None else ""

                    # Extract actual target URL from DuckDuckGo redirect link
                    target_url = raw_href
                    if "uddg=" in raw_href:
                        parsed = urllib.parse.parse_qs(urllib.parse.urlparse(raw_href).query)
                        if "uddg" in parsed and parsed["uddg"]:
                            target_url = parsed["uddg"][0]

                    snippet = snippet_elem.text.strip() if snippet_elem else ""

                    # Exclude ads or empty results
                    if target_url.startswith("http") and not target_url.startswith(
                        "https://duckduckgo.com"
                    ):
                        results.append(
                            {
                                "title": title,
                                "url": target_url,
                                "snippet": snippet,
                            }
                        )

                    if len(results) >= max_results:
                        break

            return ToolResult.ok(
                data={
                    "query": query,
                    "results": results,
                    "count": len(results),
                }
            )

        except Exception as e:
            return ToolResult.fail(f"Web search error: {e}")


class FetchWebPageTool(BaseTool):
    """Fetches a webpage and extracts clean, readable text content."""

    def __init__(self, timeout_seconds: float = 15.0) -> None:
        self.timeout_seconds = timeout_seconds

    @property
    def name(self) -> str:
        return "fetch_web_page"

    @property
    def description(self) -> str:
        return "Fetches and extracts clean readable text from a URL."

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.LOW

    @property
    def capability(self) -> WorkerCapability:
        return WorkerCapability.RESEARCH

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Webpage URL to fetch"},
                "max_length": {
                    "type": "integer",
                    "description": "Max characters to return",
                    "default": 10000,
                },
            },
            "required": ["url"],
        }

    async def run(self, **kwargs: Any) -> ToolResult:
        url = str(kwargs.get("url", "")).strip()
        if not url:
            return ToolResult.fail("Missing required parameter: 'url'")

        if not (url.startswith("http://") or url.startswith("https://")):
            return ToolResult.fail(
                f"Invalid URL schema (must begin with http:// or https://): '{url}'"
            )

        max_length = min(max(int(kwargs.get("max_length", 10000)), 500), 50000)
        headers = {"User-Agent": USER_AGENT}

        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_seconds, follow_redirects=True
            ) as client:
                async with client.stream("GET", url, headers=headers) as resp:
                    if resp.status_code != 200:
                        return ToolResult.fail(
                            f"HTTP GET '{url}' failed with status {resp.status_code}"
                        )

                    content_type = resp.headers.get("content-type", "").lower()
                    if any(
                        binary in content_type
                        for binary in [
                            "image/",
                            "video/",
                            "audio/",
                            "application/zip",
                            "application/pdf",
                        ]
                    ):
                        return ToolResult.fail(
                            f"Cannot parse binary content type: '{content_type}'"
                        )

                    chunks = []
                    total_bytes = 0
                    async for chunk in resp.aiter_bytes():
                        chunks.append(chunk)
                        total_bytes += len(chunk)
                        if total_bytes > MAX_CONTENT_BYTES:
                            break

            raw_html = b"".join(chunks).decode("utf-8", errors="replace")
            soup = BeautifulSoup(raw_html, "html.parser")

            # Remove non-content elements
            for tag in soup(["script", "style", "noscript", "svg", "nav", "footer", "header"]):
                tag.decompose()

            title = soup.title.string.strip() if soup.title and soup.title.string else ""
            raw_text = soup.get_text(separator="\n")
            # Normalize whitespace
            clean_lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
            clean_text = "\n".join(clean_lines)

            truncated = len(clean_text) > max_length
            final_text = clean_text[:max_length]

            return ToolResult.ok(
                data={
                    "url": url,
                    "title": title,
                    "content": final_text,
                    "truncated": truncated,
                    "length": len(final_text),
                }
            )

        except Exception as e:
            return ToolResult.fail(f"Failed to fetch webpage '{url}': {e}")


def register_web_tools(registry: ToolRegistry) -> None:
    """Registers web search and web page fetching tools."""
    search_tool = WebSearchTool()
    fetch_tool = FetchWebPageTool()

    if registry.exists(search_tool.name):
        registry.replace(search_tool)
    else:
        registry.register(search_tool)

    if registry.exists(fetch_tool.name):
        registry.replace(fetch_tool)
    else:
        registry.register(fetch_tool)
