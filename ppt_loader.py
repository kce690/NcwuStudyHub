from __future__ import annotations

from pathlib import Path


def scan_ppt_files(input_dir: Path) -> list[Path]:
    """扫描目录内所有 .pptx / .ppt 文件（递归），并按文件名排序。"""
    files: list[Path] = []
    files.extend(input_dir.rglob("*.pptx"))
    files.extend(input_dir.rglob("*.ppt"))
    files = [f for f in files if f.is_file()]
    files.sort(key=lambda p: str(p).lower())
    return files
