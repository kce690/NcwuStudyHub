from __future__ import annotations

from pathlib import Path


def scan_pptx_files(input_dir: Path) -> list[Path]:
    """Scan all .pptx files recursively and return a sorted list."""
    files: list[Path] = []
    files.extend(input_dir.rglob("*.pptx"))
    files = [f for f in files if f.is_file()]
    files.sort(key=lambda p: str(p).lower())
    return files


def scan_ppt_files(input_dir: Path) -> list[Path]:
    """
    Backward-compatible alias.
    v1 Web app only processes .pptx.
    """
    return scan_pptx_files(input_dir)
