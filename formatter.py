from __future__ import annotations

from typing import Iterable

REQUIRED_SECTIONS = ["内容概览", "详细笔记", "关键概念", "重要知识点", "复习提纲", "自测题"]


def _iter_bullet_texts(slides: list[dict]) -> Iterable[str]:
    for slide in slides:
        for item in slide.get("bullet_points", []):
            text = item.get("text", "").strip()
            if text:
                yield text


def _collect_key_concepts(slides: list[dict], max_items: int = 10) -> list[str]:
    concepts: list[str] = []
    seen: set[str] = set()

    for slide in slides:
        title = slide.get("title", "").strip()
        if title and title not in seen:
            concepts.append(title)
            seen.add(title)
            if len(concepts) >= max_items:
                return concepts

    for text in _iter_bullet_texts(slides):
        if text not in seen:
            concepts.append(text)
            seen.add(text)
            if len(concepts) >= max_items:
                return concepts
    return concepts


def build_raw_text_markdown(doc_title: str, slides: list[dict]) -> str:
    lines = [f"# {doc_title} - 原始提取文本", ""]
    for slide in slides:
        slide_no = slide["slide_number"]
        title = slide.get("title", f"第{slide_no}页")
        lines.append(f"## Slide {slide_no}: {title}")

        text_blocks = slide.get("text_blocks", [])
        if text_blocks:
            lines.append("### 文本块")
            for idx, block in enumerate(text_blocks, start=1):
                lines.append(f"{idx}. {block}")
        else:
            lines.append("（无可提取文本）")

        bullet_points = slide.get("bullet_points", [])
        if bullet_points:
            lines.append("### 项目符号")
            for item in bullet_points:
                indent = "  " * int(item.get("level", 0))
                lines.append(f"{indent}- {item.get('text', '')}")

        image_paths = slide.get("image_paths", [])
        if image_paths:
            lines.append("### 图片")
            for img in image_paths:
                lines.append(f"- {img}")

        if not text_blocks and image_paths:
            lines.append("> 该页主要为图片内容")

        lines.append("")
    return "\n".join(lines).strip() + "\n"


def build_ai_source_markdown(doc_title: str, slides: list[dict]) -> str:
    lines = [f"# PPT 提取内容：{doc_title}", ""]
    for slide in slides:
        slide_no = slide["slide_number"]
        lines.append(f"## Slide {slide_no}")
        lines.append(f"- 标题：{slide.get('title', f'第{slide_no}页')}")

        text_blocks = slide.get("text_blocks", [])
        if text_blocks:
            lines.append("- 文本：")
            for block in text_blocks:
                lines.append(f"  - {block}")
        else:
            lines.append("- 文本：无")

        bullet_points = slide.get("bullet_points", [])
        if bullet_points:
            lines.append("- 项目符号：")
            for item in bullet_points:
                lines.append(f"  - level={item.get('level', 0)}: {item.get('text', '')}")
        else:
            lines.append("- 项目符号：无")

        image_paths = slide.get("image_paths", [])
        if image_paths:
            lines.append("- 图片（请在详细笔记中保留这些链接）：")
            for img in image_paths:
                lines.append(f"  - ![]({img})")
        else:
            lines.append("- 图片：无")

        if not text_blocks and image_paths:
            lines.append("- 备注：该页主要为图片内容")

        lines.append("")
    return "\n".join(lines).strip()


def _build_image_supplement(slides: list[dict]) -> str:
    lines = ["## 详细笔记（按页图片补充）", ""]
    has_any_image = False
    for slide in slides:
        image_paths = slide.get("image_paths", [])
        if not image_paths:
            continue
        has_any_image = True
        slide_no = slide["slide_number"]
        title = slide.get("title", f"第{slide_no}页")
        lines.append(f"### 第{slide_no}页：{title}")

        text_blocks = slide.get("text_blocks", [])
        if text_blocks:
            lines.append(text_blocks[0])
        else:
            lines.append("该页主要为图片内容。")

        for img in image_paths:
            lines.append(f"![第{slide_no}页图片]({img})")
        lines.append("")

    if not has_any_image:
        return ""
    return "\n".join(lines).strip()


def _build_fallback_note(doc_title: str, slides: list[dict]) -> str:
    concepts = _collect_key_concepts(slides, max_items=8)
    bullet_texts = list(_iter_bullet_texts(slides))

    lines = [f"# {doc_title}", ""]
    lines.append("## 内容概览")
    lines.append(f"- 总页数：{len(slides)}")
    lines.append(f"- 图片页数量：{sum(1 for s in slides if s.get('image_paths'))}")
    lines.append("- 说明：该版本为自动回退模板，建议检查原始提取内容。")
    lines.append("")

    lines.append("## 详细笔记")
    for slide in slides:
        slide_no = slide["slide_number"]
        title = slide.get("title", f"第{slide_no}页")
        lines.append(f"### 第{slide_no}页：{title}")
        text_blocks = slide.get("text_blocks", [])
        if text_blocks:
            for block in text_blocks:
                lines.append(block)
        else:
            if slide.get("image_paths"):
                lines.append("该页主要为图片内容。")
            else:
                lines.append("原文不清晰")
        for img in slide.get("image_paths", []):
            lines.append(f"![第{slide_no}页图片]({img})")
        lines.append("")

    lines.append("## 关键概念")
    if concepts:
        for concept in concepts:
            lines.append(f"- {concept}")
    else:
        lines.append("- 原文不清晰")
    lines.append("")

    lines.append("## 重要知识点")
    if bullet_texts:
        for text in bullet_texts[:12]:
            lines.append(f"- {text}")
    else:
        lines.append("- 原文不清晰")
    lines.append("")

    lines.append("## 复习提纲")
    lines.append("1. 先通读“内容概览”和“关键概念”。")
    lines.append("2. 按“详细笔记”逐页复盘，重点关注定义、结论、步骤。")
    lines.append("3. 对照“重要知识点”进行口头复述和默写。")
    lines.append("")

    lines.append("## 自测题")
    lines.append("1. 本文档中最核心的 3 个概念是什么？")
    lines.append("2. 任选一页，概述其关键知识点与应用场景。")
    lines.append("3. 哪些内容在原文中不清晰，需要回看课件？")
    return "\n".join(lines).strip() + "\n"


def build_final_note(doc_title: str, slides: list[dict], ai_note: str | None) -> str:
    if not ai_note:
        return _build_fallback_note(doc_title, slides)

    note = ai_note.strip()
    if not note.startswith("#"):
        note = f"# {doc_title}\n\n{note}"

    for section in REQUIRED_SECTIONS:
        marker = f"## {section}"
        if marker not in note:
            note += f"\n\n{marker}\n原文不清晰"

    image_supplement = _build_image_supplement(slides)
    if image_supplement:
        note += f"\n\n{image_supplement}"

    return note.strip() + "\n"
