"""N.A.N.I. V2 — Universal Document, Article & System Manual Ingestion
Extracts readable text, structure, and digest chunks from web articles, local files,
PDFs, and Linux man pages for rapid multi-model learning.
"""

import asyncio
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import httpx
from bs4 import BeautifulSoup

from nani.core.task import RiskLevel, WorkerCapability
from nani.tools.registry import BaseTool, ToolRegistry
from nani.tools.result import ToolResult

USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 NANI/2.0"
MAX_DOC_BYTES = 1_000_000  # 1MB limit for memory protection


class DocumentReader:
    """Universal document extractor and chunker."""

    @classmethod
    async def read_url(cls, url: str, timeout_seconds: float = 20.0) -> dict[str, Any]:
        """Fetches web article and strips boilerplate, returning clean readable markdown."""
        headers = {"User-Agent": USER_AGENT}
        async with httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)

        if resp.status_code != 200:
            raise RuntimeError(f"HTTP GET returned status {resp.status_code}")

        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "noscript", "svg", "nav", "footer", "header", "aside"]):
            tag.decompose()

        title = soup.title.string.strip() if soup.title and soup.title.string else url
        raw_text = soup.get_text(separator="\n")
        lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
        content = "\n".join(lines)

        return {
            "source_type": "url",
            "source": url,
            "title": title,
            "content": content,
            "size_chars": len(content),
        }

    @classmethod
    def read_local_file(cls, file_path: str | Path, max_chars: int = 200_000) -> dict[str, Any]:
        """Reads local source file or document."""
        p = Path(file_path).expanduser().resolve()
        if not p.exists() or not p.is_file():
            raise FileNotFoundError(f"File not found: {file_path}")

        size = p.stat().st_size
        if size > MAX_DOC_BYTES:
            raise ValueError(f"File exceeds 1MB limit: {size} bytes")

        try:
            content = p.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            raise RuntimeError(f"Failed to read file: {exc}") from exc

        return {
            "source_type": "file",
            "source": str(p),
            "title": p.name,
            "content": content[:max_chars],
            "size_chars": len(content),
        }

    @classmethod
    def read_man_page(cls, command_name: str) -> dict[str, Any]:
        """Extracts plain text documentation from Linux man pages."""
        # Sanitize command name
        clean_name = command_name.replace("man:", "").strip().split()[0]
        if not shutil.which("man"):
            raise RuntimeError("Linux 'man' binary is not installed.")

        try:
            res = subprocess.run(
                ["man", clean_name],
                capture_output=True,
                text=True,
                timeout=5.0,
                check=False,
                env=dict(os.environ, PAGER="cat", MANWIDTH="80"),
            )
            if res.returncode != 0:
                raise RuntimeError(
                    f"man page for '{clean_name}' returned error: {res.stderr.strip() or 'Not found'}"
                )

            text = res.stdout.strip()
            return {
                "source_type": "man",
                "source": f"man:{clean_name}",
                "title": f"Manual for {clean_name}",
                "content": text[:100_000],
                "size_chars": len(text),
            }
        except Exception as exc:
            raise RuntimeError(f"Failed to read man page for {clean_name}: {exc}") from exc

    @classmethod
    def chunk_content(cls, content: str, chunk_size: int = 4000, overlap: int = 400) -> list[str]:
        """Splits long text into overlapping chunks for federated model summarization."""
        if len(content) <= chunk_size:
            return [content]

        chunks: list[str] = []
        start = 0
        while start < len(content):
            end = min(start + chunk_size, len(content))
            chunks.append(content[start:end])
            if end == len(content):
                break
            start += chunk_size - overlap
        return chunks


class IngestDocumentTool(BaseTool):
    """Tool to ingest articles, documents, or Linux man pages for AI learning."""

    @property
    def name(self) -> str:
        return "read_document"

    @property
    def description(self) -> str:
        return "Reads web articles (http/https), local documents, or Linux man pages (man:<cmd>)."

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
                "source": {
                    "type": "string",
                    "description": "URL, file path, or man page specifier (e.g., 'man:pactl')",
                },
                "max_chars": {
                    "type": "integer",
                    "description": "Maximum characters to return",
                    "default": 15000,
                },
            },
            "required": ["source"],
        }

    async def run(self, **kwargs: Any) -> ToolResult:
        source = str(kwargs.get("source", "")).strip()
        if not source:
            return ToolResult.fail("Missing required parameter: 'source'")

        max_chars = min(max(int(kwargs.get("max_chars", 15000)), 500), 50000)

        try:
            if source.startswith("http://") or source.startswith("https://"):
                doc = await DocumentReader.read_url(source)
            elif source.startswith("man:"):
                # Run man in threadpool to not block asyncio loop
                doc = await asyncio.to_thread(DocumentReader.read_man_page, source)
            else:
                doc = await asyncio.to_thread(
                    DocumentReader.read_local_file, source, max_chars=max_chars
                )

            content = doc["content"]
            truncated = len(content) > max_chars
            final_content = content[:max_chars]

            return ToolResult.ok(
                data={
                    "source": doc["source"],
                    "source_type": doc["source_type"],
                    "title": doc["title"],
                    "content": final_content,
                    "truncated": truncated,
                    "length": len(final_content),
                }
            )
        except Exception as exc:
            return ToolResult.fail(f"Document ingestion failed: {exc}")


def register_document_tools(registry: ToolRegistry) -> None:
    tool = IngestDocumentTool()
    if registry.exists(tool.name):
        registry.replace(tool)
    else:
        registry.register(tool)
