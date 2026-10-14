"""N.A.N.I. V2 — Native Tools Subsystem"""

from nani.tools.document_reader import DocumentReader, IngestDocumentTool, register_document_tools
from nani.tools.filesystem import (
    CopyTool,
    CreateDirectoryTool,
    FileExistsTool,
    FilesystemTool,
    ListDirectoryTool,
    MoveTool,
    PatchFileTool,
    ReadFileTool,
    SearchFilesTool,
    WriteFileTool,
    register_filesystem_tools,
)
from nani.tools.git import GitTool, register_git_tools
from nani.tools.path_utils import compute_effective_destination, resolve_safe_path
from nani.tools.process import ProcessTool, register_process_tools
from nani.tools.registry import BaseTool, DuplicateToolError, ToolRegistry
from nani.tools.result import ToolResult
from nani.tools.shell import ShellTool, register_shell_tools
from nani.tools.system_hardware import SystemHardwareTool, register_hardware_tools
from nani.tools.web_search import FetchWebPageTool, WebSearchTool, register_web_tools

__all__ = [
    "BaseTool",
    "DuplicateToolError",
    "ToolRegistry",
    "ToolResult",
    "resolve_safe_path",
    "compute_effective_destination",
    "ReadFileTool",
    "WriteFileTool",
    "PatchFileTool",
    "ListDirectoryTool",
    "SearchFilesTool",
    "FileExistsTool",
    "CreateDirectoryTool",
    "CopyTool",
    "MoveTool",
    "FilesystemTool",
    "register_filesystem_tools",
    "ShellTool",
    "register_shell_tools",
    "ProcessTool",
    "register_process_tools",
    "GitTool",
    "register_git_tools",
    "WebSearchTool",
    "FetchWebPageTool",
    "register_web_tools",
    "SystemHardwareTool",
    "register_hardware_tools",
    "DocumentReader",
    "IngestDocumentTool",
    "register_document_tools",
]
