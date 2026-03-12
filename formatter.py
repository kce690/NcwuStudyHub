from __future__ import annotations

from collections import Counter
from typing import Iterable

REQUIRED_SECTIONS = ["内容概览", "详细笔记", "关键概念", "重要知识点", "复习提纲", "自测题"]
VISUAL_HINTS = ("图", "示意", "结构", "流程", "架构", "曲线", "实验", "结果", "模型")


def _normalize_line(text: str) -> str:
    return " ".join((text or "").split()).strip()


def _dedup_keep_order(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for raw in items:
        text = _normalize_line(raw)
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _merge_fragments(lines: list[str]) -> list[str]:
    if not lines:
        return []
    merged: list[str] = []
    buffer = ""
    for line in lines:
        line = _normalize_line(line)
        if not line:
            continue
        if len(line) <= 12:
            buffer = f"{buffer} {line}".strip()
            continue
        if buffer:
            merged.append(f"{buffer}：{line}")
            buffer = ""
        else:
            merged.append(line)
    if buffer:
        merged.append(buffer)
    return merged


def _slide_plain_text(slide: dict) -> str:
    text_blocks = slide.get("text_blocks", [])
    bullets = [item.get("text", "") for item in slide.get("bullet_points", [])]
    title = slide.get("title", "")
    return " ".join([title, *text_blocks, *bullets]).strip()


def _clean_slide(slide: dict) -> dict:
    text_blocks = _merge_fragments(_dedup_keep_order(slide.get("text_blocks", [])))

    bullet_pairs = []
    seen_pair: set[tuple[int, str]] = set()
    for item in slide.get("bullet_points", []):
        level = int(item.get("level", 0) or 0)
        text = _normalize_line(item.get("text", ""))
        key = (level, text)
        if not text or key in seen_pair:
            continue
        seen_pair.add(key)
        bullet_pairs.append({"level": level, "text": text})

    return {
        "slide_number": slide.get("slide_number"),
        "title": _normalize_line(slide.get("title", "")) or f"Slide {slide.get('slide_number', '?')}",
        "text_blocks": text_blocks,
        "bullet_points": bullet_pairs,
        "image_paths": slide.get("image_paths", []),
    }


def normalize_slides(slides: list[dict]) -> list[dict]:
    return [_clean_slide(slide) for slide in slides]


def pick_key_images(slides: list[dict], max_images: int = 8) -> list[dict]:
    candidates: list[dict] = []
    for slide in slides:
        image_paths = slide.get("image_paths", [])
        if not image_paths:
            continue

        text = _slide_plain_text(slide)
        title = slide.get("title", "")
        text_size = len(_normalize_line(text))
        image_only_page = text_size < 18
        has_visual_hint = any(hint in f"{title} {text}" for hint in VISUAL_HINTS)
        priority = 3 if image_only_page else 2 if has_visual_hint else 1
        keep_count = 2 if image_only_page else 1

        for rel_path in image_paths[:keep_count]:
            candidates.append(
                {
                    "slide_number": slide.get("slide_number", 0),
                    "title": title,
                    "path": rel_path,
                    "priority": priority,
                    "caption": "本页核心为图示内容" if image_only_page else "相关图示",
                }
            )

    candidates.sort(key=lambda x: (-x["priority"], x["slide_number"], x["path"]))
    selected: list[dict] = []
    seen: set[str] = set()
    for item in candidates:
        if item["path"] in seen:
            continue
        seen.add(item["path"])
        selected.append(item)
        if len(selected) >= max_images:
            break
    return selected


def build_raw_text_markdown(doc_title: str, slides: list[dict]) -> str:
    lines = [f"# {doc_title} - 原始提取文本", ""]
    for slide in slides:
        slide_no = slide["slide_number"]
        title = slide.get("title", f"Slide {slide_no}")
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
            lines.append("> 本页核心为图示内容")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def build_ai_source_markdown(doc_title: str, slides: list[dict], basic_note: str | None = None) -> str:
    lines = [f"# PPT 提取内容: {doc_title}", ""]
    if basic_note:
        lines.extend(["## 普通模式整理结果（供参考）", basic_note.strip(), ""])

    for slide in slides:
        slide_no = slide["slide_number"]
        lines.append(f"## Slide {slide_no}")
        lines.append(f"- 标题: {slide.get('title', f'Slide {slide_no}')}")

        text_blocks = slide.get("text_blocks", [])
        if text_blocks:
            lines.append("- 文本:")
            for block in text_blocks:
                lines.append(f"  - {block}")
        else:
            lines.append("- 文本: 无")

        bullet_points = slide.get("bullet_points", [])
        if bullet_points:
            lines.append("- 项目符号:")
            for item in bullet_points:
                lines.append(f"  - level={item.get('level', 0)}: {item.get('text', '')}")
        else:
            lines.append("- 项目符号: 无")

        image_paths = slide.get("image_paths", [])
        if image_paths:
            lines.append("- 图片（仅在强相关时使用）:")
            for img in image_paths:
                lines.append(f"  - {img}")
        else:
            lines.append("- 图片: 无")
        lines.append("")
    return "\n".join(lines).strip()


def _collect_key_points(slides: list[dict], max_items: int = 14) -> list[str]:
    counter: Counter[str] = Counter()
    for slide in slides:
        for item in slide.get("bullet_points", []):
            text = item.get("text", "").strip()
            if len(text) >= 3:
                counter[text] += 1
        for text in slide.get("text_blocks", []):
            text = text.strip()
            if len(text) >= 6:
                counter[text] += 1
    return [text for text, _ in counter.most_common(max_items)]


def build_basic_note(doc_title: str, slides: list[dict]) -> tuple[str, list[dict]]:
    cleaned = normalize_slides(slides)
    key_images = pick_key_images(cleaned)

    image_map: dict[int, list[dict]] = {}
    for item in key_images:
        image_map.setdefault(item["slide_number"], []).append(item)

    lines = [f"# {doc_title}", ""]
    lines.append("## 内容概览")
    lines.append(f"- 总页数: {len(cleaned)}")
    lines.append(f"- 含图页数: {sum(1 for s in cleaned if s.get('image_paths'))}")
    topics = [s["title"] for s in cleaned if s.get("title")]
    if topics:
        lines.append(f"- 主要主题: {' / '.join(topics[:8])}")
    lines.append("")

    lines.append("## 详细笔记")
    for slide in cleaned:
        slide_no = slide["slide_number"]
        title = slide["title"]
        lines.append(f"### 第{slide_no}页: {title}")

        text_blocks = slide.get("text_blocks", [])
        bullets = slide.get("bullet_points", [])
        if text_blocks:
            for text in text_blocks[:4]:
                lines.append(f"- {text}")
        if bullets:
            lines.append("- 重点条目:")
            for item in bullets[:8]:
                indent = "  " * min(int(item.get("level", 0)), 2)
                lines.append(f"{indent}- {item.get('text', '')}")

        if not text_blocks and not bullets:
            if slide.get("image_paths"):
                lines.append("- 本页核心为图示内容。")
            else:
                lines.append("- 原文不清晰")

        for image_item in image_map.get(slide_no, []):
            lines.append(f"![第{slide_no}页图示]({image_item['path']})")
            lines.append(f"> 图示说明: {image_item['caption']}")
        lines.append("")

    lines.append("## 重点知识点")
    key_points = _collect_key_points(cleaned)
    if key_points:
        for point in key_points:
            lines.append(f"- {point}")
    else:
        lines.append("- 原文不清晰")
    lines.append("")

    if key_images:
        lines.append("## 关键图示")
        for image_item in key_images:
            lines.append(f"- 第{image_item['slide_number']}页: {image_item['caption']}")
            lines.append(f"  ![]({image_item['path']})")
        lines.append("")

    lines.append("## 复习提纲")
    lines.append("1. 先阅读内容概览，确定章节结构。")
    lines.append("2. 按详细笔记逐页复盘定义、步骤、结论。")
    lines.append("3. 对照重点知识点完成自测。")
    lines.append("")

    lines.append("## 自测题")
    lines.append("1. 本资料的核心主题是什么？")
    lines.append("2. 任选一页，说明其关键结论与依据。")
    lines.append("3. 哪些内容需要回看原课件图示？")

    return "\n".join(lines).strip() + "\n", key_images


def build_final_note(doc_title: str, slides: list[dict], ai_note: str | None) -> str:
    if not ai_note:
        basic_note, _ = build_basic_note(doc_title, slides)
        return basic_note

    note = ai_note.strip()
    if not note.startswith("#"):
        note = f"# {doc_title}\n\n{note}"

    for section in REQUIRED_SECTIONS:
        marker = f"## {section}"
        if marker not in note:
            note += f"\n\n{marker}\n原文不清晰"

    _, key_images = build_basic_note(doc_title, slides)
    if key_images and "## 关键图示" not in note:
        note += "\n\n## 关键图示"
        for image_item in key_images:
            note += (
                f"\n- 第{image_item['slide_number']}页: {image_item['caption']}"
                f"\n  ![]({image_item['path']})"
            )

    return note.strip() + "\n"
