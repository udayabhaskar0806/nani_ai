"""Unit tests for Phase 1 native tools: Filesystem, Shell, Process, and Git."""

import os
from pathlib import Path

import pytest

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
    resolve_safe_path,
)
from nani.tools.git import GitTool
from nani.tools.process import ProcessTool
from nani.tools.shell import ShellTool


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "sandbox"
    ws.mkdir()
    return ws


# --- Filesystem Tests ---


def test_filesystem_boundary_validation(workspace: Path):
    # Path inside workspace resolves safely
    safe = resolve_safe_path("nested/file.txt", workspace)
    assert safe == (workspace / "nested/file.txt").resolve()

    # Traversal escaping workspace raises PermissionError
    with pytest.raises(PermissionError, match="outside authorized workspace"):
        resolve_safe_path("../../etc/shadow", workspace)

    with pytest.raises(PermissionError, match="outside authorized workspace"):
        resolve_safe_path("/etc/passwd", workspace)


@pytest.mark.asyncio
async def test_filesystem_crud_operations(workspace: Path):
    write_tool = WriteFileTool(workspace)
    read_tool = ReadFileTool(workspace)
    patch_tool = PatchFileTool(workspace)
    exists_tool = FileExistsTool(workspace)

    # 1. Write file
    w_res = await write_tool.run(path="src/main.c", content="int main() { return 0; }")
    assert w_res.success is True
    assert (workspace / "src/main.c").is_file()

    # 2. Check existence
    e_res = await exists_tool.run(path="src/main.c")
    assert e_res.success is True
    assert e_res.data["exists"] is True
    assert e_res.data["is_file"] is True

    # 3. Read file
    r_res = await read_tool.run(path="src/main.c")
    assert r_res.success is True
    assert r_res.data["content"] == "int main() { return 0; }"

    # 4. Patch file
    p_res = await patch_tool.run(path="src/main.c", search="return 0;", replace="return 1;")
    assert p_res.success is True
    r_res2 = await read_tool.run(path="src/main.c")
    assert r_res2.data["content"] == "int main() { return 1; }"


@pytest.mark.asyncio
async def test_filesystem_directory_and_copy_move(workspace: Path):
    mkdir_tool = CreateDirectoryTool(workspace)
    list_tool = ListDirectoryTool(workspace)
    copy_tool = CopyTool(workspace)
    move_tool = MoveTool(workspace)
    search_tool = SearchFilesTool(workspace)
    write_tool = WriteFileTool(workspace)

    # Create directories and files
    await mkdir_tool.run(path="docs")
    await write_tool.run(path="docs/readme.txt", content="Documentation")
    await write_tool.run(path="docs/guide.md", content="Guide")

    # List directory
    l_res = await list_tool.run(path="docs")
    assert l_res.success is True
    assert l_res.data["count"] == 2

    # Search files
    s_res = await search_tool.run(path="docs", pattern="*.md")
    assert s_res.success is True
    assert "guide.md" in s_res.data["matches"][0]

    # Copy file
    c_res = await copy_tool.run(src="docs/guide.md", dst="docs/guide_backup.md")
    assert c_res.success is True
    assert (workspace / "docs/guide_backup.md").is_file()

    # Move file
    m_res = await move_tool.run(src="docs/guide_backup.md", dst="docs/moved_guide.md")
    assert m_res.success is True
    assert not (workspace / "docs/guide_backup.md").exists()
    assert (workspace / "docs/moved_guide.md").is_file()


@pytest.mark.asyncio
async def test_filesystem_composite_tool(workspace: Path):
    fs_tool = FilesystemTool(workspace)
    res = await fs_tool.run(operation="write_file", path="test.txt", content="Composite test")
    assert res.success is True
    assert (workspace / "test.txt").read_text() == "Composite test"


# --- Shell Tests ---


@pytest.mark.asyncio
async def test_shell_tool_success(workspace: Path):
    shell = ShellTool(workspace)
    res = await shell.run(command="echo 'NANI_SHELL_OK'")
    assert res.success is True
    assert res.exit_code == 0
    assert "NANI_SHELL_OK" in res.stdout


@pytest.mark.asyncio
async def test_shell_tool_non_zero_exit(workspace: Path):
    shell = ShellTool(workspace)
    res = await shell.run(command="ls non_existent_file_xyz_123")
    assert res.success is False
    assert res.exit_code != 0
    assert res.exit_code > 0


@pytest.mark.asyncio
async def test_shell_tool_timeout(workspace: Path):
    shell = ShellTool(workspace, default_timeout=0.2)
    res = await shell.run(command="sleep 2")
    assert res.success is False
    assert res.exit_code == -1
    assert "timed out" in res.error.lower()


@pytest.mark.asyncio
async def test_shell_tool_boundary_protection(workspace: Path):
    shell = ShellTool(workspace)
    res = await shell.run(command="echo hi", cwd="../../etc")
    assert res.success is False
    assert "outside authorized workspace" in res.error.lower()


# --- Process Tests ---


@pytest.mark.asyncio
async def test_process_tool_listing_and_info(workspace: Path):
    tool = ProcessTool(workspace)
    list_res = await tool.run(operation="list_processes", limit=5)
    assert list_res.success is True
    assert len(list_res.data["processes"]) > 0

    my_pid = os.getpid()
    info_res = await tool.run(operation="process_info", pid=my_pid)
    assert info_res.success is True
    assert info_res.data["pid"] == my_pid


@pytest.mark.asyncio
async def test_process_tool_protects_nani_process(workspace: Path):
    tool = ProcessTool(workspace)
    my_pid = os.getpid()

    # Attempting to terminate NANI itself must be rejected
    term_res = await tool.run(operation="terminate_process", pid=my_pid)
    assert term_res.success is False
    assert "Refusing to terminate protected" in term_res.error

    # Attempting to terminate init (PID 1)
    init_res = await tool.run(operation="terminate_process", pid=1)
    assert init_res.success is False


# --- Git Tests ---


@pytest.mark.asyncio
async def test_git_tool_read_only_inspection(workspace: Path):
    git_tool = GitTool(workspace)

    # Initialize a temporary git repo in the workspace
    shell = ShellTool(workspace)
    await shell.run(
        command="git init && git config user.email 'nani@test.local' && git config user.name 'NANI Test'"
    )
    (workspace / "sample.txt").write_text("Hello git")
    await shell.run(command="git add sample.txt && git commit -m 'Initial commit'")

    # Git status
    st_res = await git_tool.run(operation="status")
    assert st_res.success is True

    # Git log
    log_res = await git_tool.run(operation="log")
    assert log_res.success is True
    assert "Initial commit" in log_res.stdout

    # Git rev-parse
    rev_res = await git_tool.run(operation="rev_parse")
    assert rev_res.success is True
    assert len(rev_res.stdout.strip()) == 40


@pytest.mark.asyncio
async def test_git_tool_blocks_forbidden_commands(workspace: Path):
    git_tool = GitTool(workspace)

    # Push is not allowed in Phase 1
    push_res = await git_tool.run(operation="status", args=["push"])
    assert push_res.success is False
    assert "Forbidden" in push_res.error
