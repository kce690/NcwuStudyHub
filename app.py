from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import gradio as gr
from dotenv import load_dotenv

from ai_writer import chat_with_note
from processor import process_ppt_files


@lru_cache(maxsize=1)
def _load_ios_css() -> str:
    css_path = Path(__file__).resolve().parent / "ui" / "ios_jobs.css"
    if css_path.exists():
        return css_path.read_text(encoding="utf-8")
    return ""


@lru_cache(maxsize=1)
def _load_ios_js() -> str:
    js_path = Path(__file__).resolve().parent / "ui" / "ios_jobs.js"
    if js_path.exists():
        return js_path.read_text(encoding="utf-8")
    return ""


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


def _history_to_pairs(history_messages: list[tuple[str, str]] | None) -> list[tuple[str, str]]:
    return (history_messages or [])[-6:]


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
            gr.update(visible=True),
            gr.update(visible=False),
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
        gr.update(visible=False),
        gr.update(visible=True),
    )


def on_select_file(choice: str, state: dict):
    selected_info, raw_preview, gallery_items, note_preview, note_file = _render_selected_file(
        choice, state or {"results": [], "choices": []}
    )
    return selected_info, raw_preview, gallery_items, note_preview, note_file, []




def on_mode_change(mode: str):
    show_ai = "AI" in (mode or "")
    return gr.update(visible=show_ai)


def back_to_upload():
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
        gr.update(visible=True),
        gr.update(visible=False),
    )


def clear_chat():
    return []


def chat_submit(
    user_message: str | None,
    history: list[tuple[str, str]] | None,
    selected_choice: str | None,
    state: dict,
    api_key: str,
    api_base: str,
    model: str,
):
    history = history or []
    question = (user_message or "").strip()
    if not question:
        return history, None

    idx = _get_selected_index(selected_choice, state or {"results": [], "choices": []})
    results = (state or {}).get("results", [])
    if idx < 0 or idx >= len(results):
        history.append((question, "请先上传并处理 PPT，再进行提问。"))
        return history, None

    item = results[idx]
    current_note = item.get("note_preview", "")
    current_raw = item.get("raw_text_preview", "")

    reply, err = chat_with_note(
        user_message=question,
        current_note_markdown=current_note,
        current_raw_text=current_raw,
        api_key=api_key.strip() or os.getenv("DEEPSEEK_API_KEY"),
        api_base=api_base.strip() or os.getenv("DEEPSEEK_BASE_URL"),
        model=model.strip() or os.getenv("DEEPSEEK_MODEL"),
        history=_history_to_pairs(history),
    )
    history.append((question, reply if reply else err or "当前资料中没有足够信息"))
    return history, None


def build_ui() -> gr.Blocks:
    load_dotenv()
    default_api_base = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
    default_model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

    with gr.Blocks(title="NCWUStudyHub", fill_width=True) as demo:
        state = gr.State({"results": [], "choices": []})
        gr.HTML(f"<style>{_load_ios_css()}</style>")
        gr.HTML(f"<script>{_load_ios_js()}</script>")

        with gr.Column(elem_id="app-shell"):
            with gr.Column(elem_id="upload-screen", elem_classes=["ios-glass"], visible=True) as upload_screen:
                gr.Markdown("## NCWUStudyHub\n### 上传 PPT，开始你的学习会话", elem_id="hero-title")
                upload_files = gr.File(
                    label="上传 .pptx 文件（可多选）",
                    file_count="multiple",
                    file_types=[".pptx"],
                    type="filepath",
                )
                mode_radio = gr.Radio(label="处理模式", choices=["普通模式", "AI 增强模式"], value="普通模式")
                with gr.Column(visible=False) as ai_config_wrap:
                    api_key = gr.Textbox(label="DeepSeek API Key", type="password", placeholder="AI 增强模式必填")
                    api_base = gr.Textbox(label="DeepSeek Base URL", value=default_api_base)
                    model = gr.Textbox(label="DeepSeek Model", value=default_model)
                output_dir = gr.Textbox(label="输出目录", value="./output_notes_web")
                start_btn = gr.Button("生成笔记", variant="primary", size="lg", elem_id="start-btn")

            with gr.Column(elem_id="chat-screen", visible=False) as chat_screen:
                with gr.Row():
                    back_btn = gr.Button("← 返回上传页", variant="secondary")
                with gr.Row():
                    with gr.Column(scale=8, elem_classes=["ios-glass"]):
                        status_md = gr.Markdown("### 处理摘要\n- 尚未开始", elem_id="status-pill")
                        file_picker = gr.Dropdown(label="文件", choices=[], value=None)
                        selected_info = gr.Markdown("暂无结果")
                        note_preview = gr.Markdown(elem_id="workspace-note")
                    with gr.Column(scale=4, elem_classes=["ios-glass"]):
                        logs_box = gr.Textbox(label="处理日志", lines=12)
                        result_table = gr.Dataframe(
                            headers=["文件名", "模式", "状态", "页数", "图片数", "AI", "输出目录", "信息"],
                            datatype=["str", "str", "str", "number", "number", "str", "str", "str"],
                            interactive=False,
                            label="结果总览",
                        )
                        raw_preview = gr.Markdown(label="原始提取预览")
                        image_gallery = gr.Gallery(label="图片预览", columns=2, height=220, type="filepath")
                        note_download = gr.File(label="下载 note.md")
                with gr.Column(elem_classes=["ios-glass"]):
                    chatbot = gr.Chatbot(label="学习助手", elem_id="chat-window")
                    chat_input = gr.Dropdown(
                        label="",
                        choices=["这份笔记的核心知识点是什么？", "请按考试重点给我3分钟速记版", "帮我按章节生成复习清单", "请解释最难的三个概念并举例"],
                        value=None,
                        allow_custom_value=True,
                        elem_id="chat-question",
                    )
                    with gr.Row():
                        send_btn = gr.Button("发送", variant="primary")
                        clear_chat_btn = gr.Button("清空对话")

        mode_radio.change(
            fn=on_mode_change,
            inputs=[mode_radio],
            outputs=[ai_config_wrap],
        )

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
                upload_screen,
                chat_screen,
            ],
        )

        file_picker.change(
            fn=on_select_file,
            inputs=[file_picker, state],
            outputs=[selected_info, raw_preview, image_gallery, note_preview, note_download, chatbot],
        )

        back_btn.click(
            fn=back_to_upload,
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
                upload_screen,
                chat_screen,
            ],
        )

        send_btn.click(
            fn=chat_submit,
            inputs=[chat_input, chatbot, file_picker, state, api_key, api_base, model],
            outputs=[chatbot, chat_input],
        )
        clear_chat_btn.click(fn=clear_chat, outputs=[chatbot])

    return demo


if __name__ == "__main__":
    app = build_ui()
    app.launch(server_name="0.0.0.0", server_port=7860, share=False)
