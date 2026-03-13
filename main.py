from __future__ import annotations

import argparse
import os
from pathlib import Path

from dotenv import load_dotenv

from ai_writer import AIWriter
from ppt_loader import scan_pptx_files
from processor import process_single_pptx
from utils import ensure_dir, setup_console_logger


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="NCWUStudyHub CLI: .pptx -> 学习笔记")
    parser.add_argument("--input", required=True, help="输入目录，例如 ./input_ppt")
    parser.add_argument("--output", required=True, help="输出目录，例如 ./output_notes")
    parser.add_argument("--mode", choices=["basic", "ai"], default="basic", help="处理模式：basic 或 ai")
    parser.add_argument("--model", default=None, help="覆盖模型名")
    parser.add_argument("--api-base", default=None, help="覆盖 API Base URL")
    parser.add_argument("--max-files", type=int, default=None, help="最多处理 N 个文件")
    parser.add_argument("--overwrite", action="store_true", help="覆盖已存在输出目录")
    parser.add_argument("--verbose", action="store_true", help="显示详细日志")
    return parser.parse_args()


def main() -> int:
    load_dotenv()
    args = parse_args()
    logger = setup_console_logger(args.verbose)

    input_dir = Path(args.input).resolve()
    output_dir = ensure_dir(Path(args.output).resolve())
    if not input_dir.exists() or not input_dir.is_dir():
        logger.error("输入目录不存在或不是目录: %s", input_dir)
        return 1

    pptx_files = scan_pptx_files(input_dir)
    if args.max_files is not None and args.max_files > 0:
        pptx_files = pptx_files[: args.max_files]
    if not pptx_files:
        print(f"未找到可处理的 .pptx 文件。输出目录：{output_dir}")
        return 0

    writer = AIWriter(
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        api_base=args.api_base or os.getenv("DEEPSEEK_BASE_URL"),
        model=args.model or os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
        logger=logger,
    )

    if args.mode == "ai" and not writer.is_available():
        logger.warning("当前为 AI 增强模式，但 API 未配置，处理时会自动降级普通模式。")

    success_count = 0
    fail_count = 0
    for src_file in pptx_files:
        result = process_single_pptx(
            src_file=src_file,
            output_root=output_dir,
            overwrite=args.overwrite,
            ai_writer=writer,
            mode=args.mode,
            status_callback=lambda m: logger.info(m),
        )
        if result.get("success"):
            success_count += 1
        else:
            fail_count += 1

    print(f"处理完成：成功 {success_count}，失败 {fail_count}，输出目录：{output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
