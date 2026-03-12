from __future__ import annotations

import argparse
import os
import shutil
from pathlib import Path

from dotenv import load_dotenv

from ai_writer import AIWriter
from extractor import extract_pptx_content
from formatter import build_ai_source_markdown, build_final_note, build_raw_text_markdown
from ppt_converter import convert_ppt_to_pptx
from ppt_loader import scan_ppt_files
from utils import (
    ensure_dir,
    now_iso,
    safe_name,
    setup_console_logger,
    setup_file_logger,
    write_json,
    write_text,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="NCWUStudyHub: PPT -> Markdown 学习笔记工具")
    parser.add_argument("--input", required=True, help="输入目录，例如 ./input_ppt")
    parser.add_argument("--output", required=True, help="输出目录，例如 ./output_notes")
    parser.add_argument("--model", default=None, help="AI 模型名（覆盖 .env 中 OPENAI_MODEL）")
    parser.add_argument("--api-base", default=None, help="API Base URL（覆盖 .env 中 OPENAI_BASE_URL）")
    parser.add_argument("--max-files", type=int, default=None, help="最多处理多少个文件")
    parser.add_argument("--overwrite", action="store_true", help="若输出目录已存在则覆盖")
    parser.add_argument("--verbose", action="store_true", help="显示详细日志")
    return parser.parse_args()


def process_one_file(
    src_file: Path,
    output_root: Path,
    overwrite: bool,
    ai_writer: AIWriter,
    console_logger,
) -> bool:
    folder_name = safe_name(src_file.stem)
    target_dir = output_root / folder_name

    if target_dir.exists():
        if overwrite:
            shutil.rmtree(target_dir)
        else:
            console_logger.warning("跳过 %s：输出目录已存在（可加 --overwrite）", src_file.name)
            return False

    ensure_dir(target_dir)
    images_dir = ensure_dir(target_dir / "images")
    process_log_path = target_dir / "process.log"
    file_logger = setup_file_logger(process_log_path)

    meta = {
        "source_file": str(src_file.resolve()),
        "source_name": src_file.name,
        "source_suffix": src_file.suffix.lower(),
        "processed_at": now_iso(),
        "success": False,
        "slide_count": 0,
        "image_count": 0,
        "ai_used": False,
        "ai_error": None,
        "error": None,
    }

    try:
        file_logger.info("开始处理：%s", src_file)
        working_pptx = src_file

        if src_file.suffix.lower() == ".ppt":
            converted_path = target_dir / f"{safe_name(src_file.stem)}_converted.pptx"
            file_logger.info("检测到 .ppt，尝试转换为 .pptx")
            converted = convert_ppt_to_pptx(src_file, converted_path, file_logger)
            if not converted:
                meta["error"] = ".ppt 转换失败，已跳过"
                file_logger.error(meta["error"])
                write_json(target_dir / "meta.json", meta)
                return False
            working_pptx = converted_path

        slides, stats = extract_pptx_content(working_pptx, images_dir, file_logger)
        meta["slide_count"] = stats["slide_count"]
        meta["image_count"] = stats["image_count"]

        raw_text_md = build_raw_text_markdown(src_file.stem, slides)
        write_text(target_dir / "raw_text.md", raw_text_md)

        cleaned_data = {
            "source_file": src_file.name,
            "slide_count": stats["slide_count"],
            "image_count": stats["image_count"],
            "slides": slides,
        }
        write_json(target_dir / "cleaned_slides.json", cleaned_data)

        ai_source = build_ai_source_markdown(src_file.stem, slides)
        ai_note, ai_error = ai_writer.generate_note(src_file.stem, ai_source)
        if ai_error:
            meta["ai_error"] = ai_error
            file_logger.warning("AI 生成失败，将使用回退笔记模板：%s", ai_error)
        else:
            meta["ai_used"] = True

        final_note = build_final_note(src_file.stem, slides, ai_note)
        write_text(target_dir / "note.md", final_note)

        meta["success"] = True
        file_logger.info("处理完成：%s", src_file.name)
        return True
    except Exception as exc:  # noqa: BLE001
        meta["error"] = str(exc)
        file_logger.exception("处理失败：%s", exc)
        return False
    finally:
        write_json(target_dir / "meta.json", meta)
        for handler in list(file_logger.handlers):
            handler.close()
            file_logger.removeHandler(handler)


def main() -> int:
    load_dotenv()
    args = parse_args()
    logger = setup_console_logger(args.verbose)

    input_dir = Path(args.input).resolve()
    output_dir = ensure_dir(Path(args.output).resolve())

    if not input_dir.exists() or not input_dir.is_dir():
        logger.error("输入目录不存在或不是目录：%s", input_dir)
        return 1

    ppt_files = scan_ppt_files(input_dir)
    if args.max_files is not None and args.max_files > 0:
        ppt_files = ppt_files[: args.max_files]

    if not ppt_files:
        print(f"未找到可处理文件（.ppt/.pptx）。输出目录：{output_dir}")
        return 0

    ai_writer = AIWriter(
        api_key=os.getenv("OPENAI_API_KEY"),
        api_base=args.api_base or os.getenv("OPENAI_BASE_URL"),
        model=args.model or os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        logger=logger,
    )

    success_count = 0
    fail_count = 0

    for src_file in ppt_files:
        ok = process_one_file(
            src_file=src_file,
            output_root=output_dir,
            overwrite=args.overwrite,
            ai_writer=ai_writer,
            console_logger=logger,
        )
        if ok:
            success_count += 1
        else:
            fail_count += 1

    print(f"处理完成：成功 {success_count}，失败 {fail_count}，输出目录：{output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
