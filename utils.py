from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def safe_name(name: str) -> str:
    """
    生成可作为文件夹名的安全名称（兼容 Windows）。
    """
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .")
    cleaned = re.sub(r"\s+", "_", cleaned)
    return cleaned or "untitled"


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def write_text(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def setup_console_logger(verbose: bool = False) -> logging.Logger:
    logger = logging.getLogger("ncwu_studyhub")
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    logger.handlers.clear()
    logger.propagate = False

    formatter = logging.Formatter("[%(levelname)s] %(message)s")
    handler = logging.StreamHandler()
    handler.setLevel(logging.DEBUG if verbose else logging.INFO)
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return logger


def setup_file_logger(log_file: Path) -> logging.Logger:
    logger_name = f"ncwu_studyhub.file.{log_file.parent.name}"
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()
    logger.propagate = False

    ensure_dir(log_file.parent)
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    file_handler = logging.FileHandler(log_file, mode="w", encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    return logger
