"""N.A.N.I. V2 — Structured Filesystem Native Tools
Provides safe, boundary-enforced file and directory manipulation.
Strictly forbids path traversal outside the authorized workspace.
"""

import fnmatch
import os
import shutil
from pathlib import Path
from typing import Any

from nani.core.task import RiskLevel, WorkerCapability
from nani.tools.registry import BaseTool, ToolRegistry
from nani.tools.result import ToolResult


def resolve_safe_path(path: str | Path, workspace_path: str | Path | None = None) -> Path:
    """Normalizes and verifies that the target path resides within the authorized workspace.

    Raises PermissionError if path traversal escapes the workspace.
    """
    ws = Path(workspace_path or Path.cwd()).resolve()
    target = Path(path)
    if not target.is_absolute():
        resolved = (ws / target).resolve()
    else:
        resolved = target.resolve()

    try:
        resolved.relative_to(ws)
    except ValueError:
        raise PermissionError(
            f"Access denied: path '{path}' is outside authorized workspace '{ws}'."
        ) from None
    return resolved


class ReadFileTool(BaseTool):
    def __init__(self, workspace_path: Path | None = None) -> None:
        self.workspace_path = workspace_path

    @property
    def name(self) -> str:
        return "read_file"

    @property
    def description(self) -> str:
        return "Reads the text content of a file within the authorized workspace."

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.LOW

    @property
    def capability(self) -> WorkerCapability:
        return WorkerCapability.CODING

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative or workspace-bounded file path",
                },
                "offset": {"type": "integer", "description": "Byte offset", "default": 0},
                "limit": {"type": "integer", "description": "Maximum bytes to read"},
                "workspace_path": {
                    "type": "string",
                    "description": "Optional workspace root override",
                },
            },
            "required": ["path"],
        }

    async def run(self, **kwargs: Any) -> ToolResult:
        path_str = str(kwargs.get("path", ""))
        ws = kwargs.get("workspace_path") or self.workspace_path
        try:
            target = resolve_safe_path(path_str, ws)
            if not target.is_file():
                return ToolResult.fail(f"File not found: {path_str}")

            with open(target, encoding="utf-8", errors="replace") as f:
                offset = int(kwargs.get("offset", 0))
                if offset > 0:
                    f.seek(offset)
                limit = kwargs.get("limit")
                content = f.read(int(limit)) if limit is not None else f.read()

            return ToolResult.ok(
                data={
                    "path": str(target),
                    "content": content,
                    "bytes_read": len(content.encode("utf-8")),
                }
            )
        except PermissionError as pe:
            return ToolResult.fail(str(pe))
        except Exception as e:
            return ToolResult.fail(f"Failed to read file '{path_str}': {e}")


class WriteFileTool(BaseTool):
    def __init__(self, workspace_path: Path | None = None) -> None:
        self.workspace_path = workspace_path

    @property
    def name(self) -> str:
        return "write_file"

    @property
    def description(self) -> str:
        return (
            "Writes content to a file within the workspace. Creates parent directories if needed."
        )

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.MEDIUM

    @property
    def capability(self) -> WorkerCapability:
        return WorkerCapability.CODING

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative or workspace-bounded file path",
                },
                "content": {"type": "string", "description": "Text content to write"},
                "create_dirs": {"type": "boolean", "default": True},
                "workspace_path": {
                    "type": "string",
                    "description": "Optional workspace root override",
                },
            },
            "required": ["path", "content"],
        }

    async def run(self, **kwargs: Any) -> ToolResult:
        path_str = str(kwargs.get("path", ""))
        content = str(kwargs.get("content", ""))
        ws = kwargs.get("workspace_path") or self.workspace_path
        try:
            target = resolve_safe_path(path_str, ws)
            if kwargs.get("create_dirs", True):
                target.parent.mkdir(parents=True, exist_ok=True)

            with open(target, "w", encoding="utf-8") as f:
                f.write(content)

            return ToolResult.ok(
                data={"path": str(target), "bytes_written": len(content.encode("utf-8"))}
            )
        except PermissionError as pe:
            return ToolResult.fail(str(pe))
        except Exception as e:
            return ToolResult.fail(f"Failed to write file '{path_str}': {e}")


class PatchFileTool(BaseTool):
    def __init__(self, workspace_path: Path | None = None) -> None:
        self.workspace_path = workspace_path

    @property
    def name(self) -> str:
        return "patch_file"

    @property
    def description(self) -> str:
        return "Finds and replaces targeted strings inside an existing file."

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.MEDIUM

    @property
    def capability(self) -> WorkerCapability:
        return WorkerCapability.CODING

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Target file path"},
                "search": {"type": "string", "description": "Exact text or regex pattern to match"},
                "replace": {"type": "string", "description": "Replacement text"},
                "workspace_path": {
                    "type": "string",
                    "description": "Optional workspace root override",
                },
            },
            "required": ["path", "search", "replace"],
        }

    async def run(self, **kwargs: Any) -> ToolResult:
        path_str = str(kwargs.get("path", ""))
        search_str = str(kwargs.get("search", ""))
        replace_str = str(kwargs.get("replace", ""))
        ws = kwargs.get("workspace_path") or self.workspace_path
        try:
            target = resolve_safe_path(path_str, ws)
            if not target.is_file():
                return ToolResult.fail(f"File not found for patching: {path_str}")

            with open(target, encoding="utf-8") as f:
                original = f.read()

            if search_str not in original:
                return ToolResult.fail(f"Search target not found in file '{path_str}'")

            patched = original.replace(search_str, replace_str)
            with open(target, "w", encoding="utf-8") as f:
                f.write(patched)

            return ToolResult.ok(
                data={"path": str(target), "replacements": original.count(search_str)}
            )
        except PermissionError as pe:
            return ToolResult.fail(str(pe))
        except Exception as e:
            return ToolResult.fail(f"Failed to patch file '{path_str}': {e}")


class ListDirectoryTool(BaseTool):
    def __init__(self, workspace_path: Path | None = None) -> None:
        self.workspace_path = workspace_path

    @property
    def name(self) -> str:
        return "list_directory"

    @property
    def description(self) -> str:
        return "Lists files and subdirectories within a directory in the workspace."

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.LOW

    @property
    def capability(self) -> WorkerCapability:
        return WorkerCapability.SYSTEM

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Directory path", "default": "."},
                "workspace_path": {
                    "type": "string",
                    "description": "Optional workspace root override",
                },
            },
        }

    async def run(self, **kwargs: Any) -> ToolResult:
        path_str = str(kwargs.get("path", "."))
        ws = kwargs.get("workspace_path") or self.workspace_path
        try:
            target = resolve_safe_path(path_str, ws)
            if not target.is_dir():
                return ToolResult.fail(f"Directory not found: {path_str}")

            entries = []
            for item in sorted(target.iterdir()):
                entries.append(
                    {
                        "name": item.name,
                        "is_dir": item.is_dir(),
                        "size": item.stat().st_size if item.is_file() else 0,
                    }
                )
            return ToolResult.ok(
                data={"path": str(target), "entries": entries, "count": len(entries)}
            )
        except PermissionError as pe:
            return ToolResult.fail(str(pe))
        except Exception as e:
            return ToolResult.fail(f"Failed to list directory '{path_str}': {e}")


class SearchFilesTool(BaseTool):
    def __init__(self, workspace_path: Path | None = None) -> None:
        self.workspace_path = workspace_path

    @property
    def name(self) -> str:
        return "search_files"

    @property
    def description(self) -> str:
        return "Searches for files matching glob pattern within the workspace."

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.LOW

    @property
    def capability(self) -> WorkerCapability:
        return WorkerCapability.SYSTEM

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Base directory to search in",
                    "default": ".",
                },
                "pattern": {
                    "type": "string",
                    "description": "Glob pattern (e.g. *.c)",
                    "default": "*",
                },
                "workspace_path": {
                    "type": "string",
                    "description": "Optional workspace root override",
                },
            },
        }

    async def run(self, **kwargs: Any) -> ToolResult:
        path_str = str(kwargs.get("path", "."))
        pattern = str(kwargs.get("pattern", "*"))
        ws = kwargs.get("workspace_path") or self.workspace_path
        try:
            target = resolve_safe_path(path_str, ws)
            if not target.is_dir():
                return ToolResult.fail(f"Directory not found: {path_str}")

            matches = []
            for root, _, files in os.walk(target):
                for f in files:
                    if fnmatch.fnmatch(f, pattern):
                        full_p = Path(root) / f
                        rel_p = full_p.relative_to(target)
                        matches.append(str(rel_p))

            return ToolResult.ok(data={"matches": matches, "count": len(matches)})
        except PermissionError as pe:
            return ToolResult.fail(str(pe))
        except Exception as e:
            return ToolResult.fail(f"Failed to search files: {e}")


class FileExistsTool(BaseTool):
    def __init__(self, workspace_path: Path | None = None) -> None:
        self.workspace_path = workspace_path

    @property
    def name(self) -> str:
        return "file_exists"

    @property
    def description(self) -> str:
        return "Checks if a file or directory exists within the authorized workspace."

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.LOW

    @property
    def capability(self) -> WorkerCapability:
        return WorkerCapability.SYSTEM

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to check"},
                "workspace_path": {
                    "type": "string",
                    "description": "Optional workspace root override",
                },
            },
            "required": ["path"],
        }

    async def run(self, **kwargs: Any) -> ToolResult:
        path_str = str(kwargs.get("path", ""))
        ws = kwargs.get("workspace_path") or self.workspace_path
        try:
            target = resolve_safe_path(path_str, ws)
            exists = target.exists()
            return ToolResult.ok(
                data={
                    "path": str(target),
                    "exists": exists,
                    "is_file": target.is_file() if exists else False,
                    "is_dir": target.is_dir() if exists else False,
                }
            )
        except PermissionError as pe:
            return ToolResult.fail(str(pe))
        except Exception as e:
            return ToolResult.fail(f"Failed to check file '{path_str}': {e}")


class CreateDirectoryTool(BaseTool):
    def __init__(self, workspace_path: Path | None = None) -> None:
        self.workspace_path = workspace_path

    @property
    def name(self) -> str:
        return "create_directory"

    @property
    def description(self) -> str:
        return "Creates a directory (and required parent directories) within the workspace."

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.LOW

    @property
    def capability(self) -> WorkerCapability:
        return WorkerCapability.SYSTEM

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Directory path to create"},
                "workspace_path": {
                    "type": "string",
                    "description": "Optional workspace root override",
                },
            },
            "required": ["path"],
        }

    async def run(self, **kwargs: Any) -> ToolResult:
        path_str = str(kwargs.get("path", ""))
        ws = kwargs.get("workspace_path") or self.workspace_path
        try:
            target = resolve_safe_path(path_str, ws)
            target.mkdir(parents=True, exist_ok=True)
            return ToolResult.ok(data={"path": str(target), "created": True})
        except PermissionError as pe:
            return ToolResult.fail(str(pe))
        except Exception as e:
            return ToolResult.fail(f"Failed to create directory '{path_str}': {e}")


class CopyTool(BaseTool):
    def __init__(self, workspace_path: Path | None = None) -> None:
        self.workspace_path = workspace_path

    @property
    def name(self) -> str:
        return "copy"

    @property
    def description(self) -> str:
        return "Copies a file from source to destination within the authorized workspace."

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.LOW

    @property
    def capability(self) -> WorkerCapability:
        return WorkerCapability.SYSTEM

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "src": {"type": "string", "description": "Source path"},
                "dst": {"type": "string", "description": "Destination path"},
                "workspace_path": {
                    "type": "string",
                    "description": "Optional workspace root override",
                },
            },
            "required": ["src", "dst"],
        }

    async def run(self, **kwargs: Any) -> ToolResult:
        src_str = str(kwargs.get("src", ""))
        dst_str = str(kwargs.get("dst", ""))
        ws = kwargs.get("workspace_path") or self.workspace_path
        try:
            src = resolve_safe_path(src_str, ws)
            dst = resolve_safe_path(dst_str, ws)
            if not src.is_file():
                return ToolResult.fail(f"Source file not found: {src_str}")
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            return ToolResult.ok(data={"src": str(src), "dst": str(dst)})
        except PermissionError as pe:
            return ToolResult.fail(str(pe))
        except Exception as e:
            return ToolResult.fail(f"Failed to copy '{src_str}' to '{dst_str}': {e}")


class MoveTool(BaseTool):
    def __init__(self, workspace_path: Path | None = None) -> None:
        self.workspace_path = workspace_path

    @property
    def name(self) -> str:
        return "move"

    @property
    def description(self) -> str:
        return "Moves a file from source to destination within the authorized workspace."

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.MEDIUM

    @property
    def capability(self) -> WorkerCapability:
        return WorkerCapability.SYSTEM

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "src": {"type": "string", "description": "Source path"},
                "dst": {"type": "string", "description": "Destination path"},
                "workspace_path": {
                    "type": "string",
                    "description": "Optional workspace root override",
                },
            },
            "required": ["src", "dst"],
        }

    async def run(self, **kwargs: Any) -> ToolResult:
        src_str = str(kwargs.get("src", ""))
        dst_str = str(kwargs.get("dst", ""))
        ws = kwargs.get("workspace_path") or self.workspace_path
        try:
            src = resolve_safe_path(src_str, ws)
            dst = resolve_safe_path(dst_str, ws)
            if not src.exists():
                return ToolResult.fail(f"Source not found: {src_str}")
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(src, dst)
            return ToolResult.ok(data={"src": str(src), "dst": str(dst)})
        except PermissionError as pe:
            return ToolResult.fail(str(pe))
        except Exception as e:
            return ToolResult.fail(f"Failed to move '{src_str}' to '{dst_str}': {e}")


class FilesystemTool(BaseTool):
    """Composite filesystem tool supporting operation multiplexing."""

    def __init__(self, workspace_path: Path | None = None) -> None:
        self.workspace_path = workspace_path
        self._subtools: dict[str, BaseTool] = {
            "read_file": ReadFileTool(workspace_path),
            "write_file": WriteFileTool(workspace_path),
            "patch_file": PatchFileTool(workspace_path),
            "list_directory": ListDirectoryTool(workspace_path),
            "search_files": SearchFilesTool(workspace_path),
            "file_exists": FileExistsTool(workspace_path),
            "create_directory": CreateDirectoryTool(workspace_path),
            "copy": CopyTool(workspace_path),
            "move": MoveTool(workspace_path),
        }

    @property
    def name(self) -> str:
        return "filesystem"

    @property
    def description(self) -> str:
        return "Unified filesystem operations tool (read, write, patch, list, search, exists, mkdir, copy, move)."

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.MEDIUM

    @property
    def capability(self) -> WorkerCapability:
        return WorkerCapability.CODING

    async def run(self, **kwargs: Any) -> ToolResult:
        operation = kwargs.get("operation")
        if not operation:
            return ToolResult.fail("Missing required parameter: 'operation'")
        subtool = self._subtools.get(str(operation))
        if not subtool:
            return ToolResult.fail(f"Unknown filesystem operation: '{operation}'")
        sub_args = {k: v for k, v in kwargs.items() if k != "operation"}
        return await subtool.run(**sub_args)


def register_filesystem_tools(registry: ToolRegistry, workspace_path: Path | None = None) -> None:
    """Registers all filesystem tools into the provided ToolRegistry."""
    tools = [
        ReadFileTool(workspace_path),
        WriteFileTool(workspace_path),
        PatchFileTool(workspace_path),
        ListDirectoryTool(workspace_path),
        SearchFilesTool(workspace_path),
        FileExistsTool(workspace_path),
        CreateDirectoryTool(workspace_path),
        CopyTool(workspace_path),
        MoveTool(workspace_path),
        FilesystemTool(workspace_path),
    ]
    for tool in tools:
        if registry.exists(tool.name):
            registry.replace(tool)
        else:
            registry.register(tool)
