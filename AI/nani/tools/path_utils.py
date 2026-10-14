"""N.A.N.I. V2 — Safe Path Resolution and Symlink Traversal Protection
Provides canonical workspace path confinement and symlink inspection.
Strictly zero imports of core or tools to prevent circular import dependencies.
"""

import os
from pathlib import Path


def resolve_safe_path(
    path: str | Path,
    workspace_path: str | Path | None = None,
    allow_symlink: bool = True,
) -> Path:
    """Normalizes and verifies that the target path resides within the authorized workspace.

    Enforces:
    1. Canonical resolution within authorized workspace root.
    2. Verification that intermediate path components do not escape workspace via symlinks.
    3. Rejection of symlinks pointing outside workspace.

    Raises PermissionError if any traversal escapes the workspace.
    """
    ws = Path(workspace_path or Path.cwd()).resolve()
    target = Path(path)

    if not target.is_absolute():
        candidate = ws / target
    else:
        candidate = target

    # Resolve symlinks and canonicalize
    resolved = candidate.resolve()

    try:
        resolved.relative_to(ws)
    except ValueError:
        raise PermissionError(
            f"Access denied: path '{path}' is outside authorized workspace '{ws}'."
        ) from None

    # Verify every component along the path does not traverse an outward symlink
    try:
        rel_parts = resolved.relative_to(ws).parts
    except ValueError:
        raise PermissionError(
            f"Access denied: path '{path}' is outside authorized workspace '{ws}'."
        ) from None

    curr = ws
    for part in rel_parts:
        curr = curr / part
        if curr.is_symlink():
            if not allow_symlink:
                raise PermissionError(
                    f"Access denied: symlink destination is forbidden for this operation: '{curr}'."
                )
            real_curr = curr.resolve()
            try:
                real_curr.relative_to(ws)
            except ValueError:
                raise PermissionError(
                    f"Access denied: symlink '{curr}' points outside authorized workspace."
                ) from None

    return resolved


def compute_effective_destination(
    src: Path,
    dst: Path,
    workspace: Path,
) -> Path:
    """Calculates the effective destination path for copy/move operations.

    If dst is an existing directory, the target is dst / src.name.
    Validates that the effective destination does not overwrite a symlink pointing outside workspace.
    """
    if dst.is_dir():
        effective = dst / src.name
    else:
        effective = dst

    # Resolve safe path without allowing symlink destination overwrite
    if effective.is_symlink() or os.path.islink(str(effective)):
        real_target = effective.resolve()
        try:
            real_target.relative_to(workspace)
        except ValueError:
            raise PermissionError(
                f"Access denied: destination '{effective}' is a symlink pointing outside workspace."
            ) from None
        raise PermissionError(
            f"Access denied: destination child '{effective}' is an existing symlink."
        )

    return resolve_safe_path(effective, workspace)
