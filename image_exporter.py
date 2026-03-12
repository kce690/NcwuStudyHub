from __future__ import annotations

from pathlib import Path

from utils import ensure_dir


def _normalize_ext(ext: str) -> str:
    ext = ext.strip(".").lower()
    if ext in {"jpeg", "jpe"}:
        return "jpg"
    if ext == "tif":
        return "tiff"
    return ext or "png"


def export_picture_shape(shape, slide_number: int, image_index: int, images_dir: Path, logger) -> str | None:
    """
    导出单个图片 shape 到 images_dir。
    成功返回相对路径（用于 Markdown），失败返回 None。
    """
    try:
        image = shape.image
        ext = _normalize_ext(image.ext)
        filename = f"slide_{slide_number:03d}_img_{image_index:02d}.{ext}"
        ensure_dir(images_dir)
        out_path = images_dir / filename
        out_path.write_bytes(image.blob)
        return f"images/{filename}"
    except Exception as exc:  # noqa: BLE001
        logger.warning("导出图片失败：slide=%s idx=%s error=%s", slide_number, image_index, exc)
        return None
