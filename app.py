from __future__ import annotations

import os
from typing import Any

import gradio as gr
from dotenv import load_dotenv

from ai_writer import chat_with_note
from processor import process_ppt_files


def _build_table_rows(results: list[dict]) -> list[list[Any]]:
    rows: list[list[Any]] = []
    for item in results:
        status = "成功" if item.get("success") else "失败"
        ai_status = "已启用" if item.get("ai_used") else "未启用/降级"
        rows.append(
            [
                item.get("file_name", ""),
                item.get("mode", "basic"),
                status,
                item.get("slide_count", 0),
                item.get("image_count", 0),
                ai_status,
                item.get("output_dir", ""),
                item.get("error") or item.get("warning") or "",
            ]
        )
    return rows


def _choice_label(index: int, file_name: str) -> str:
    return f"{index + 1}. {file_name}"


def _get_selected_index(choice: str | None, state: dict) -> int:
    choices = state.get("choices", [])
    if not choices:
        return -1
    if choice in choices:
        return choices.index(choice)
    return 0


def _render_selected_file(choice: str | None, state: dict):
    results = state.get("results", [])
    idx = _get_selected_index(choice, state)
    if idx < 0 or idx >= len(results):
        return "暂无结果", "", [], "", None

    item = results[idx]
    status_line = "成功" if item.get("success") else "失败"
    ai_line = "已启用" if item.get("ai_used") else "未启用或已降级"
    info = [
        f"### 文件：{item.get('file_name', '')}",
        f"- 模式：`{item.get('mode', 'basic')}`",
        f"- 状态：{status_line}",
        f"- 页数：{item.get('slide_count', 0)}",
        f"- 图片数：{item.get('image_count', 0)}",
        f"- AI 增强：{ai_line}",
        f"- 输出目录：`{item.get('output_dir', '')}`",
    ]
    if item.get("warning"):
        info.append(f"- 提示：{item['warning']}")
    if item.get("error"):
        info.append(f"- 错误：{item['error']}")

    raw_preview = item.get("raw_text_preview", "") or "（无原始文本）"
    note_preview = item.get("note_preview", "") or "（未生成笔记）"
    gallery_items = item.get("gallery_images", []) or []
    note_file = item.get("note_path") or None
    return "\n".join(info), raw_preview, gallery_items, note_preview, note_file


def _history_to_pairs(history_messages: list[dict] | None) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    pending_user: str | None = None
    for msg in history_messages or []:
        role = (msg or {}).get("role")
        content = str((msg or {}).get("content", ""))
        if role == "user":
            pending_user = content
        elif role == "assistant":
            if pending_user is not None:
                pairs.append((pending_user, content))
                pending_user = None
    return pairs[-6:]


def run_processing(
    uploaded_files,
    mode: str,
    api_key: str,
    api_base: str,
    model: str,
    output_dir: str,
    progress=gr.Progress(track_tqdm=False),
):
    if not uploaded_files:
        empty_state = {"results": [], "choices": []}
        return (
            "### 处理摘要\n- 尚未开始",
            "请先上传至少一个 .pptx 文件。",
            [],
            gr.update(choices=[], value=None),
            "暂无结果",
            "",
            [],
            "",
            None,
            empty_state,
            [],
        )

    total = len(uploaded_files)
    update_counter = {"count": 0}

    def on_status(msg: str) -> None:
        update_counter["count"] += 1
        fraction = min(update_counter["count"] / (total * 7), 0.98)
        progress(fraction, desc=msg)

    mode = (mode or "普通模式").strip()
    mode_value = "basic" if "普通" in mode else "ai"
    summary = process_ppt_files(
        uploaded_files=uploaded_files,
        mode=mode_value,
        api_key=api_key.strip() or None,
        api_base=api_base.strip() or None,
        model=model.strip() or None,
        output_dir=output_dir.strip() or "./output_notes_web",
        overwrite=True,
        status_callback=on_status,
    )
    progress(1.0, desc="处理完成")

    results = summary["results"]
    rows = _build_table_rows(results)
    choices = [_choice_label(i, item.get("file_name", f"file_{i+1}")) for i, item in enumerate(results)]
    state = {"results": results, "choices": choices}
    default_choice = choices[0] if choices else None
    selected_info, raw_preview, gallery_items, note_preview, note_file = _render_selected_file(default_choice, state)

    status_md = (
        f"### 处理摘要\n"
        f"- 模式：`{summary.get('mode', mode_value)}`\n"
        f"- 成功：{summary['success_count']}\n"
        f"- 失败：{summary['fail_count']}\n"
        f"- 输出目录：`{summary['output_dir']}`"
    )
    return (
        status_md,
        summary["logs"],
        rows,
        gr.update(choices=choices, value=default_choice),
        selected_info,
        raw_preview,
        gallery_items,
        note_preview,
        note_file,
        state,
        [],
    )


def on_select_file(choice: str, state: dict):
    selected_info, raw_preview, gallery_items, note_preview, note_file = _render_selected_file(
        choice, state or {"results": [], "choices": []}
    )
    return selected_info, raw_preview, gallery_items, note_preview, note_file, []


def clear_results():
    empty_state = {"results": [], "choices": []}
    return (
        "### 处理摘要\n- 尚未开始",
        "",
        [],
        gr.update(choices=[], value=None),
        "暂无结果",
        "",
        [],
        "",
        None,
        empty_state,
        [],
    )


def clear_chat():
    return []


def chat_submit(
    user_message: str,
    history: list[dict] | None,
    selected_choice: str | None,
    state: dict,
    api_key: str,
    api_base: str,
    model: str,
):
    history = history or []
    question = (user_message or "").strip()
    if not question:
        return history, ""

    idx = _get_selected_index(selected_choice, state or {"results": [], "choices": []})
    results = (state or {}).get("results", [])
    if idx < 0 or idx >= len(results):
        history.append({"role": "user", "content": question})
        history.append({"role": "assistant", "content": "请先上传并处理 PPT，再进行提问。"})
        return history, ""

    item = results[idx]
    current_note = item.get("note_preview", "")
    current_raw = item.get("raw_text_preview", "")

    reply, err = chat_with_note(
        user_message=question,
        current_note_markdown=current_note,
        current_raw_text=current_raw,
        api_key=api_key.strip() or os.getenv("OPENAI_API_KEY"),
        api_base=api_base.strip() or os.getenv("OPENAI_BASE_URL"),
        model=model.strip() or os.getenv("OPENAI_MODEL"),
        history=_history_to_pairs(history),
    )
    history.append({"role": "user", "content": question})
    history.append({"role": "assistant", "content": reply if reply else err or "当前资料中没有足够信息"})
    return history, ""


def build_ui() -> gr.Blocks:
    load_dotenv()
    default_api_base = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    default_model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    with gr.Blocks(title="NCWUStudyHub", fill_width=True) as demo:
        state = gr.State({"results": [], "choices": []})

        with gr.Row():
            with gr.Column(scale=1):
                gr.Markdown(
                    "## NCWUStudyHub\n"
                    "上传 PPT，自动整理为大学生可复习的学习笔记。"
                )
                upload_files = gr.File(
                    label="上传 .pptx 文件（可多选）",
                    file_count="multiple",
                    file_types=[".pptx"],
                    type="filepath",
                )
                mode_radio = gr.Radio(
                    label="处理模式",
                    choices=["普通模式", "AI 增强模式"],
                    value="普通模式",
                )
                api_key = gr.Textbox(label="API Key", type="password", placeholder="普通模式可留空")
                api_base = gr.Textbox(label="Base URL", value=default_api_base)
                model = gr.Textbox(label="Model", value=default_model)
                output_dir = gr.Textbox(label="输出目录", value="./output_notes_web")
                with gr.Row():
                    start_btn = gr.Button("开始处理", variant="primary")
                    clear_btn = gr.Button("清空结果")

            with gr.Column(scale=2):
                status_md = gr.Markdown("### 处理摘要\n- 尚未开始")
                logs_box = gr.Textbox(label="处理日志", lines=10)
                result_table = gr.Dataframe(
                    headers=["文件名", "模式", "状态", "页数", "图片数", "AI", "输出目录", "信息"],
                    datatype=["str", "str", "str", "number", "number", "str", "str", "str"],
                    interactive=False,
                    label="文件结果总览",
                )
                file_picker = gr.Dropdown(label="选择文件查看详情", choices=[], value=None)
                selected_info = gr.Markdown("暂无结果")
                gr.Markdown("#### 原始提取文本预览")
                raw_preview = gr.Markdown()
                gr.Markdown("#### 最终学习笔记预览")
                note_preview = gr.Markdown()
                image_gallery = gr.Gallery(label="关键图片预览", columns=4, height=240, type="filepath")
                note_download = gr.File(label="下载 note.md")

            with gr.Column(scale=1):
                gr.Markdown(
                    "## AI 问答区\n"
                    "基于中间区域当前选中文件的笔记内容进行追问。"
                )
                chatbot = gr.Chatbot(
                    label="学习助手对话",
                    height=560,
                    placeholder="请先在中间区域生成并选择一个文件结果。",
                )
                chat_input = gr.Textbox(label="输入问题", placeholder="例如：这一章讲了什么？")
                with gr.Row():
                    send_btn = gr.Button("发送")
                    clear_chat_btn = gr.Button("清空对话")

        start_btn.click(
            fn=run_processing,
            inputs=[upload_files, mode_radio, api_key, api_base, model, output_dir],
            outputs=[
                status_md,
                logs_box,
                result_table,
                file_picker,
                selected_info,
                raw_preview,
                image_gallery,
                note_preview,
                note_download,
                state,
                chatbot,
            ],
        )

        file_picker.change(
            fn=on_select_file,
            inputs=[file_picker, state],
            outputs=[selected_info, raw_preview, image_gallery, note_preview, note_download, chatbot],
        )

        clear_btn.click(
            fn=clear_results,
            outputs=[
                status_md,
                logs_box,
                result_table,
                file_picker,
                selected_info,
                raw_preview,
                image_gallery,
                note_preview,
                note_download,
                state,
                chatbot,
            ],
        )

        send_btn.click(
            fn=chat_submit,
            inputs=[chat_input, chatbot, file_picker, state, api_key, api_base, model],
            outputs=[chatbot, chat_input],
        )
        chat_input.submit(
            fn=chat_submit,
            inputs=[chat_input, chatbot, file_picker, state, api_key, api_base, model],
            outputs=[chatbot, chat_input],
        )
        clear_chat_btn.click(fn=clear_chat, outputs=[chatbot])

    return demo


if __name__ == "__main__":
    app = build_ui()
    app.launch(server_name="127.0.0.1", server_port=7860, share=False)
