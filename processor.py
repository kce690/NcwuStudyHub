from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Callable

from ai_writer import AIWriter
from extractor import extract_pptx_content
from formatter import build_ai_source_markdown, build_basic_note, build_final_note, build_raw_text_markdown
from utils import ensure_dir, now_iso, safe_name, setup_file_logger, write_json, write_text

StatusCallback = Callable[[str], None]


def _empty_result(file_name: str) -> dict:
    return {
        "file_name": file_name,
        "source_file": "",
        "success": False,
        "error": None,
        "warning": None,
        "mode": "basic",
        "slide_count": 0,
        "image_count": 0,
        "ai_used": False,
        "ai_error": None,
        "output_dir": "",
        "raw_text_path": "",
        "cleaned_slides_path": "",
        "note_path": "",
        "meta_path": "",
        "process_log_path": "",
        "raw_text_preview": "",
        "note_preview": "",
        "gallery_images": [],
        "key_images": [],
    }


def process_single_pptx(
    src_file: Path,
    output_root: Path,
    overwrite: bool,
    ai_writer: AIWriter,
    mode: str = "basic",
    output_stem: str | None = None,
    status_callback: StatusCallback | None = None,
) -> dict:
    result = _empty_result(src_file.name)
    result["source_file"] = str(src_file.resolve())
    result["mode"] = mode

    def emit(msg: str) -> None:
        if status_callback:
            status_callback(msg)

    if src_file.suffix.lower() != ".pptx":
        result["error"] = "仅支持 .pptx 文件"
        emit(f"[{src_file.name}] 跳过：仅支持 .pptx")
        return result

    folder_name = safe_name(output_stem or src_file.stem)
    target_dir = output_root / folder_name
    result["output_dir"] = str(target_dir.resolve())

    if target_dir.exists():
        if overwrite:
            shutil.rmtree(target_dir)
        else:
            result["error"] = "输出目录已存在（可开启 overwrite）"
            emit(f"[{src_file.name}] 失败：输出目录已存在")
            return result

    ensure_dir(target_dir)
    images_dir = ensure_dir(target_dir / "images")
    process_log_path = target_dir / "process.log"
    file_logger = setup_file_logger(process_log_path)
    result["process_log_path"] = str(process_log_path.resolve())

    meta = {
        "source_file": str(src_file.resolve()),
        "source_name": src_file.name,
        "source_suffix": src_file.suffix.lower(),
        "processed_at": now_iso(),
        "mode": mode,
        "success": False,
        "slide_count": 0,
        "image_count": 0,
        "ai_used": False,
        "ai_error": None,
        "error": None,
    }

    try:
        emit(f"[{src_file.name}] 正在读取文件")
        file_logger.info("开始处理: %s", src_file)

        emit(f"[{src_file.name}] 正在提取文字")
        emit(f"[{src_file.name}] 正在导出图片")
        slides, stats = extract_pptx_content(src_file, images_dir, file_logger)
        meta["slide_count"] = stats["slide_count"]
        meta["image_count"] = stats["image_count"]
        result["slide_count"] = stats["slide_count"]
        result["image_count"] = stats["image_count"]

        raw_text_md = build_raw_text_markdown(src_file.stem, slides)
        raw_text_path = target_dir / "raw_text.md"
        write_text(raw_text_path, raw_text_md)
        result["raw_text_path"] = str(raw_text_path.resolve())
        result["raw_text_preview"] = raw_text_md

        cleaned_data = {
            "source_file": src_file.name,
            "slide_count": stats["slide_count"],
            "image_count": stats["image_count"],
            "slides": slides,
        }
        cleaned_slides_path = target_dir / "cleaned_slides.json"
        write_json(cleaned_slides_path, cleaned_data)
        result["cleaned_slides_path"] = str(cleaned_slides_path.resolve())

        basic_note, key_images = build_basic_note(src_file.stem, slides)
        final_note = basic_note
        result["key_images"] = key_images
        result["gallery_images"] = [str((target_dir / item["path"]).resolve()) for item in key_images]

        requested_ai = mode == "ai"
        ai_error = None
        if requested_ai:
            if ai_writer.is_available():
                emit(f"[{src_file.name}] 正在调用 AI 增强")
                ai_source = build_ai_source_markdown(src_file.stem, slides, basic_note=basic_note)
                ai_note, ai_error = ai_writer.generate_note(src_file.stem, ai_source)
                if ai_error:
                    file_logger.warning("AI 增强失败，自动降级普通模式: %s", ai_error)
                else:
                    final_note = build_final_note(src_file.stem, slides, ai_note)
                    result["ai_used"] = True
                    meta["ai_used"] = True
            else:
                ai_error = "AI 增强模式需要有效 API Key"
                file_logger.warning(ai_error)

            if ai_error:
                result["ai_error"] = ai_error
                meta["ai_error"] = ai_error
                result["warning"] = "AI 未启用或生成失败，已自动降级为普通模式结果"

        note_path = target_dir / "note.md"
        write_text(note_path, final_note)
        result["note_path"] = str(note_path.resolve())
        result["note_preview"] = final_note

        result["success"] = True
        meta["success"] = True
        file_logger.info("处理完成: %s", src_file.name)
        emit(f"[{src_file.name}] 处理完成")
        return result
    except Exception as exc:  # noqa: BLE001
        error_text = str(exc)
        result["error"] = error_text
        meta["error"] = error_text
        file_logger.exception("处理失败: %s", exc)
        emit(f"[{src_file.name}] 处理失败: {error_text}")
        return result
    finally:
        meta_path = target_dir / "meta.json"
        write_json(meta_path, meta)
        result["meta_path"] = str(meta_path.resolve())
        for handler in list(file_logger.handlers):
            handler.close()
            file_logger.removeHandler(handler)


def process_ppt_files(
    uploaded_files,
    mode: str = "basic",
    api_key: str | None = None,
    api_base: str | None = None,
    model: str | None = None,
    output_dir: str = "./output_notes_web",
    overwrite: bool = True,
    status_callback: StatusCallback | None = None,
) -> dict:
    output_root = ensure_dir(Path(output_dir).resolve())
    temp_root = ensure_dir(Path("temp").resolve())
    session_dir = ensure_dir(temp_root / f"uploads_{now_iso().replace(':', '-').replace('+', '_')}")

    logs: list[str] = []

    def emit(msg: str) -> None:
        logs.append(msg)
        if status_callback:
            status_callback(msg)

    mode = (mode or "basic").strip().lower()
    if mode not in {"basic", "ai"}:
        mode = "basic"

    writer = AIWriter(
        api_key=api_key or os.getenv("DEEPSEEK_API_KEY"),
        api_base=api_base or os.getenv("DEEPSEEK_BASE_URL"),
        model=model or os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
        logger=None,
    )

    uploaded_files = uploaded_files or []
    if not uploaded_files:
        return {
            "logs": "未上传文件",
            "results": [],
            "success_count": 0,
            "fail_count": 0,
            "output_dir": str(output_root),
            "mode": mode,
        }

    if mode == "ai" and not writer.is_available():
        emit("当前选择 AI 增强模式，但未配置有效 API Key，将自动降级为普通模式结果。")

    results: list[dict] = []
    used_stems: dict[str, int] = {}
    total = len(uploaded_files)
    for idx, file_obj in enumerate(uploaded_files, start=1):
        source_path = getattr(file_obj, "name", file_obj)
        src_file = Path(str(source_path))
        emit(f"[{idx}/{total}] 准备处理 {src_file.name}")
        item_result = _empty_result(src_file.name)
        item_result["mode"] = mode
        item_result["source_file"] = str(src_file)

        try:
            if src_file.suffix.lower() != ".pptx":
                item_result["error"] = "仅支持 .pptx 文件"
                emit(f"[{src_file.name}] 文件格式不支持，已跳过")
                results.append(item_result)
                continue

            copied_name = f"{idx:03d}_{safe_name(src_file.name)}"
            copied_path = session_dir / copied_name
            shutil.copy2(src_file, copied_path)

            base_stem = safe_name(src_file.stem)
            used_stems[base_stem] = used_stems.get(base_stem, 0) + 1
            output_stem = base_stem if used_stems[base_stem] == 1 else f"{base_stem}_{used_stems[base_stem]}"

            item_result = process_single_pptx(
                src_file=copied_path,
                output_root=output_root,
                overwrite=overwrite,
                ai_writer=writer,
                mode=mode,
                output_stem=output_stem,
                status_callback=emit,
            )
            item_result["file_name"] = src_file.name
            results.append(item_result)
        except Exception as exc:  # noqa: BLE001
            item_result["error"] = str(exc)
            emit(f"[{src_file.name}] 处理失败: {exc}")
            results.append(item_result)
    success_count = sum(1 for r in results if r.get("success"))
    fail_count = len(results) - success_count
    emit(f"处理完成：成功 {success_count}，失败 {fail_count}，输出目录：{output_root}")

    return {
        "logs": "\n".join(logs),
        "results": results,
        "success_count": success_count,
        "fail_count": fail_count,
        "output_dir": str(output_root),
        "mode": mode,
    }
