from __future__ import annotations

import copy
import os
import shutil
from pathlib import Path
from typing import Callable, Generator

from ai_writer import AIWriter
from extractor import extract_pptx_content
from formatter import (
    build_incremental_note,
    build_raw_text_markdown,
    build_slide_basic_block,
    normalize_slides,
    pick_key_images,
)
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
        "processed_units": 0,
        "total_units": 0,
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


def _resolve_uploaded_source(file_obj) -> str:
    if isinstance(file_obj, dict):
        return str(file_obj.get("path") or file_obj.get("name") or "")

    path_attr = getattr(file_obj, "path", None)
    if path_attr:
        return str(path_attr)

    name_attr = getattr(file_obj, "name", None)
    if name_attr:
        return str(name_attr)

    return str(file_obj or "")


def _snapshot_result(result: dict) -> dict:
    return copy.deepcopy(result)


def process_single_pptx_stream(
    src_file: Path,
    output_root: Path,
    overwrite: bool,
    ai_writer: AIWriter,
    mode: str = "basic",
    output_stem: str | None = None,
    status_callback: StatusCallback | None = None,
) -> Generator[dict, None, dict]:
    result = _empty_result(src_file.name)
    result["source_file"] = str(src_file.resolve())
    result["mode"] = mode

    def emit(status: str, file_progress: float) -> dict:
        if status_callback:
            status_callback(status)
        return {"status": status, "file_progress": max(0.0, min(file_progress, 1.0)), "result": _snapshot_result(result)}

    if src_file.suffix.lower() != ".pptx":
        result["error"] = "仅支持 .pptx 文件"
        event = emit(f"[{src_file.name}] 跳过：仅支持 .pptx", 1.0)
        yield event
        return event["result"]

    folder_name = safe_name(output_stem or src_file.stem)
    target_dir = output_root / folder_name

    if target_dir.exists():
        if overwrite:
            try:
                shutil.rmtree(target_dir)
            except OSError:
                suffix = now_iso().replace(":", "-").replace("+", "_")
                fallback_name = f"{folder_name}_{suffix}"
                target_dir = output_root / fallback_name
                index = 1
                while target_dir.exists():
                    target_dir = output_root / f"{fallback_name}_{index}"
                    index += 1
                result["warning"] = f"输出目录被占用，已自动切换到 {target_dir.name}"
                yield emit(f"[{src_file.name}] 输出目录占用，已切换到 {target_dir.name}", 0.01)
        else:
            result["error"] = "输出目录已存在（可开启 overwrite）"
            event = emit(f"[{src_file.name}] 失败：输出目录已存在", 1.0)
            yield event
            return event["result"]

    result["output_dir"] = str(target_dir.resolve())
    ensure_dir(target_dir)
    images_dir = ensure_dir(target_dir / "images")
    process_log_path = target_dir / "process.log"
    note_path = target_dir / "note.md"
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
        yield emit(f"[{src_file.name}] 正在读取文件", 0.02)
        file_logger.info("开始处理: %s", src_file)

        yield emit(f"[{src_file.name}] 正在提取文字与图片", 0.05)
        slides_raw, stats = extract_pptx_content(src_file, images_dir, file_logger)
        slides = normalize_slides(slides_raw)
        key_images = pick_key_images(slides)

        meta["slide_count"] = stats["slide_count"]
        meta["image_count"] = stats["image_count"]
        result["slide_count"] = stats["slide_count"]
        result["image_count"] = stats["image_count"]
        result["total_units"] = max(len(slides), 1)

        raw_text_md = build_raw_text_markdown(src_file.stem, slides_raw)
        raw_text_path = target_dir / "raw_text.md"
        write_text(raw_text_path, raw_text_md)
        result["raw_text_path"] = str(raw_text_path.resolve())
        result["raw_text_preview"] = raw_text_md

        cleaned_data = {
            "source_file": src_file.name,
            "slide_count": stats["slide_count"],
            "image_count": stats["image_count"],
            "slides": slides_raw,
        }
        cleaned_slides_path = target_dir / "cleaned_slides.json"
        write_json(cleaned_slides_path, cleaned_data)
        result["cleaned_slides_path"] = str(cleaned_slides_path.resolve())

        requested_ai = mode == "ai"
        ai_ready = requested_ai and ai_writer.is_available()
        if requested_ai and not ai_ready:
            result["warning"] = "AI 未启用或生成失败，已自动降级为普通模式结果"
            result["ai_error"] = "AI 增强模式需要有效 API Key"
            meta["ai_error"] = result["ai_error"]
            file_logger.warning(result["ai_error"])

        blocks: list[str] = []
        gallery_seen: set[str] = set()
        gallery_paths: list[str] = []

        write_text(
            note_path,
            build_incremental_note(
                src_file.stem, blocks, 0, result["total_units"], key_images=key_images, finished=False
            ),
        )
        result["note_path"] = str(note_path.resolve())
        result["note_preview"] = note_path.read_text(encoding="utf-8")

        total_units = max(len(slides), 1)
        for idx, slide in enumerate(slides, start=1):
            yield emit(f"[{src_file.name}] 正在处理第 {idx}/{total_units} 页", (idx - 1) / total_units)

            block_md = build_slide_basic_block(slide)
            if ai_ready:
                yield emit(f"[{src_file.name}] 正在调用 AI 生成第 {idx}/{total_units} 页", (idx - 0.6) / total_units)
                ai_block, ai_error = ai_writer.generate_slide_note(src_file.stem, slide)
                if ai_block:
                    block_md = ai_block.strip()
                    result["ai_used"] = True
                    meta["ai_used"] = True
                else:
                    result["warning"] = "部分页面 AI 生成失败，已自动回退为普通模式内容"
                    result["ai_error"] = ai_error
                    meta["ai_error"] = ai_error
                    file_logger.warning("第 %s 页 AI 生成失败，回退普通模式: %s", idx, ai_error)

            blocks.append(block_md)
            result["processed_units"] = idx

            for rel_path in (slide.get("image_paths") or [])[:2]:
                abs_path = str((target_dir / rel_path).resolve())
                if abs_path not in gallery_seen:
                    gallery_seen.add(abs_path)
                    gallery_paths.append(abs_path)
            result["gallery_images"] = gallery_paths

            partial_note = build_incremental_note(
                src_file.stem, blocks, idx, total_units, key_images=key_images, finished=False
            )
            write_text(note_path, partial_note)
            result["note_preview"] = partial_note

            yield emit(f"[{src_file.name}] 已完成 {idx}/{total_units} 页", idx / total_units)

        final_note = build_incremental_note(
            src_file.stem, blocks, total_units, total_units, key_images=key_images, finished=True
        )
        write_text(note_path, final_note)
        result["note_preview"] = final_note
        result["key_images"] = key_images

        result["success"] = True
        meta["success"] = True
        file_logger.info("处理完成: %s", src_file.name)
        final_event = emit(f"[{src_file.name}] 处理完成", 1.0)
        yield final_event
        return final_event["result"]
    except Exception as exc:  # noqa: BLE001
        error_text = str(exc)
        result["error"] = error_text
        meta["error"] = error_text
        file_logger.exception("处理失败: %s", exc)
        error_event = emit(f"[{src_file.name}] 处理失败: {error_text}", 1.0)
        yield error_event
        return error_event["result"]
    finally:
        meta_path = target_dir / "meta.json"
        write_json(meta_path, meta)
        result["meta_path"] = str(meta_path.resolve())
        for handler in list(file_logger.handlers):
            handler.close()
            file_logger.removeHandler(handler)


def process_single_pptx(
    src_file: Path,
    output_root: Path,
    overwrite: bool,
    ai_writer: AIWriter,
    mode: str = "basic",
    output_stem: str | None = None,
    status_callback: StatusCallback | None = None,
) -> dict:
    final_result = _empty_result(src_file.name)
    for event in process_single_pptx_stream(
        src_file=src_file,
        output_root=output_root,
        overwrite=overwrite,
        ai_writer=ai_writer,
        mode=mode,
        output_stem=output_stem,
        status_callback=status_callback,
    ):
        final_result = event["result"]
    return final_result


def process_ppt_files_stream(
    uploaded_files,
    mode: str = "basic",
    api_key: str | None = None,
    api_base: str | None = None,
    model: str | None = None,
    output_dir: str = "./output_notes_web",
    overwrite: bool = True,
    status_callback: StatusCallback | None = None,
) -> Generator[dict, None, dict]:
    output_root = ensure_dir(Path(output_dir).resolve())
    temp_root = ensure_dir(Path("temp").resolve())
    session_dir = ensure_dir(temp_root / f"uploads_{now_iso().replace(':', '-').replace('+', '_')}")

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
    resolved = [_resolve_uploaded_source(item) for item in uploaded_files]
    total = len(resolved)

    logs: list[str] = []
    results: list[dict] = []
    for idx, source in enumerate(resolved, start=1):
        name = Path(source).name if source else f"file_{idx}"
        item = _empty_result(name)
        item["source_file"] = source
        item["mode"] = mode
        results.append(item)

    def current_summary() -> dict:
        success_count = sum(1 for r in results if r.get("success"))
        fail_count = sum(1 for r in results if r.get("error"))
        return {
            "logs": "\n".join(logs),
            "results": copy.deepcopy(results),
            "success_count": success_count,
            "fail_count": fail_count,
            "output_dir": str(output_root),
            "mode": mode,
        }

    def emit(status_text: str, progress: float, active_index: int, finished: bool = False) -> dict:
        logs.append(status_text)
        if status_callback:
            status_callback(status_text)
        return {
            "status_text": status_text,
            "progress": max(0.0, min(progress, 1.0)),
            "active_index": active_index,
            "finished": finished,
            "summary": current_summary(),
        }

    if not resolved:
        empty_event = emit("未上传文件。", 1.0, -1, finished=True)
        yield empty_event
        return empty_event

    if mode == "ai" and not writer.is_available():
        warm_event = emit("当前选择 AI 增强模式，但未配置有效 API Key，将自动降级为普通模式。", 0.0, 0, finished=False)
        yield warm_event

    used_stems: dict[str, int] = {}

    for idx, source_path in enumerate(resolved):
        src_file = Path(str(source_path))
        original_name = src_file.name if source_path else f"file_{idx + 1}"

        try:
            if not source_path:
                results[idx]["error"] = "上传文件路径无效"
                err_event = emit(f"[{idx + 1}/{total}] 文件路径无效，已跳过", (idx + 1) / total, idx, finished=False)
                yield err_event
                continue

            if src_file.suffix.lower() != ".pptx":
                results[idx]["error"] = "仅支持 .pptx 文件"
                err_event = emit(f"[{idx + 1}/{total}] {original_name} 格式不支持，已跳过", (idx + 1) / total, idx, finished=False)
                yield err_event
                continue

            copied_name = f"{idx + 1:03d}_{safe_name(src_file.name)}"
            copied_path = session_dir / copied_name
            shutil.copy2(src_file, copied_path)

            base_stem = safe_name(src_file.stem)
            used_stems[base_stem] = used_stems.get(base_stem, 0) + 1
            output_stem = base_stem if used_stems[base_stem] == 1 else f"{base_stem}_{used_stems[base_stem]}"

            for single_event in process_single_pptx_stream(
                src_file=copied_path,
                output_root=output_root,
                overwrite=overwrite,
                ai_writer=writer,
                mode=mode,
                output_stem=output_stem,
                status_callback=None,
            ):
                item_result = single_event["result"]
                item_result["file_name"] = original_name
                results[idx] = item_result

                overall_progress = (idx + single_event["file_progress"]) / total
                status_text = f"[{idx + 1}/{total}] {single_event['status']}"
                yield emit(status_text, overall_progress, idx, finished=False)
        except Exception as exc:  # noqa: BLE001
            item = _empty_result(original_name)
            item["source_file"] = str(src_file)
            item["mode"] = mode
            item["error"] = f"{type(exc).__name__}: {exc}"
            results[idx] = item
            err_event = emit(
                f"[{idx + 1}/{total}] {original_name} 处理失败：{item['error']}",
                (idx + 1) / total,
                idx,
                finished=False,
            )
            yield err_event

    final_status = f"处理完成：成功 {sum(1 for r in results if r.get('success'))}，失败 {sum(1 for r in results if r.get('error'))}"
    final_event = emit(final_status, 1.0, max(total - 1, 0), finished=True)
    yield final_event
    return final_event


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
    final_summary = {
        "logs": "",
        "results": [],
        "success_count": 0,
        "fail_count": 0,
        "output_dir": str(Path(output_dir).resolve()),
        "mode": mode,
    }
    for event in process_ppt_files_stream(
        uploaded_files=uploaded_files,
        mode=mode,
        api_key=api_key,
        api_base=api_base,
        model=model,
        output_dir=output_dir,
        overwrite=overwrite,
        status_callback=status_callback,
    ):
        final_summary = event["summary"]
    return final_summary
