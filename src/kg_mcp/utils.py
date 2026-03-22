"""Cross-platform utilities for cache directory and path normalization."""

import os
import platform
from pathlib import Path


def get_cache_dir() -> Path:
    """Return OS-appropriate cache directory for kg-mcp."""
    system = platform.system()
    if system == "Windows":
        base = Path(
            os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")
        )
    else:
        base = Path.home()
    cache_dir = base / ".kg-mcp"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def normalize_path(file_path: Path, workspace_root: Path) -> str:
    """Normalize path to relative POSIX format for cross-platform portability."""
    try:
        relative = file_path.relative_to(workspace_root)
    except ValueError:
        # If file_path is not relative to workspace_root, use as-is
        relative = file_path
    return relative.as_posix()
