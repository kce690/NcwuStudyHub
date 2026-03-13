from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import gradio as gr
from dotenv import load_dotenv

from ai_writer import chat_with_note
from processor import process_ppt_files_stream


def _patch_gradio_local_startup_request() -> None:
    # On Windows, system proxy settings can cause Gradio's localhost checks
    # (startup-events/url_ok) to go through a proxy and return 502.
    # Patch httpx for localhost only so external requests keep default behavior.
    import httpx

    def _patch_method(method_name: str) -> None:
        original = getattr(httpx, method_name, None)
        if not callable(original) or getattr(original, "_ncwu_local_patch", False):
            return

        def _patched(url, *args, **kwargs):
            url_str = str(url)
            if "127.0.0.1" in url_str or "localhost" in url_str:
                kwargs.setdefault("trust_env", False)
            return original(url, *args, **kwargs)

        _patched._ncwu_local_patch = True  # type: ignore[attr-defined]
        setattr(httpx, method_name, _patched)

    _patch_method("get")
    _patch_method("head")


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
        status = "成功" if item.get("success") else "失败" if item.get("error") else "处理中"
        ai_status = "已启用" if item.get("ai_used") else "未启用/降级"
        unit_done = int(item.get("processed_units", 0) or 0)
        unit_total = int(item.get("total_units", 0) or 0)
        rows.append(
            [
                item.get("file_name", ""),
                item.get("mode", "basic"),
                status,
                item.get("slide_count", 0),
                item.get("image_count", 0),
                f"{unit_done}/{unit_total}" if unit_total else "-",
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
        return "暂无结果", [], "（正在等待生成内容）", None

    item = results[idx]
    status_line = "成功" if item.get("success") else "失败" if item.get("error") else "处理中"
    ai_line = "已启用" if item.get("ai_used") else "未启用或已降级"
    info = [
        f"### 文件：{item.get('file_name', '')}",
        f"- 模式：`{item.get('mode', 'basic')}`",
        f"- 状态：{status_line}",
        f"- 页数：{item.get('slide_count', 0)}",
        f"- 图片数：{item.get('image_count', 0)}",
        f"- 已处理：{item.get('processed_units', 0)}/{item.get('total_units', 0)}",
        f"- AI 增强：{ai_line}",
        f"- 输出目录：`{item.get('output_dir', '')}`",
    ]
    if item.get("warning"):
        info.append(f"- 提示：{item['warning']}")
    if item.get("error"):
        info.append(f"- 错误：{item['error']}")

    note_preview = item.get("note_preview", "") or "（正在生成内容）"
    gallery_items = item.get("gallery_images", []) or []
    note_file = item.get("note_path") or None
    if note_file and not Path(str(note_file)).exists():
        note_file = None
    return "\n".join(info), gallery_items, note_preview, note_file


def _history_to_pairs(history_messages: list[tuple[str, str]] | None) -> list[tuple[str, str]]:
    return (history_messages or [])[-6:]


def _build_status_md(status_text: str, summary: dict) -> str:
    return (
        "### 处理状态\n"
        f"- 当前：{status_text}\n"
        f"- 模式：`{summary.get('mode', 'basic')}`\n"
        f"- 成功：{summary.get('success_count', 0)}\n"
        f"- 失败：{summary.get('fail_count', 0)}\n"
        f"- 输出目录：`{summary.get('output_dir', '')}`"
    )


def run_processing(
    uploaded_files,
    mode: str,
    api_key: str,
    api_base: str,
    model: str,
    output_dir: str,
    progress=gr.Progress(track_tqdm=False),
):
    progress_fn = progress if callable(progress) else None

    def update_progress(fraction: float, desc: str) -> None:
        if progress_fn:
            progress_fn(fraction, desc=desc)

    if not uploaded_files:
        gr.Warning("请先上传至少一个 .pptx 文件，再点击“开始处理”。")
        empty_state = {"results": [], "choices": []}
        yield (
            "### 处理状态\n- 尚未开始",
            "请先上传至少一个 .pptx 文件。",
            [],
            gr.update(choices=[], value=None),
            "暂无结果",
            [],
            "（正在等待生成内容）",
            None,
            empty_state,
            [],
        )
        return

    mode_text = (mode or "").strip()
    mode_value = "ai" if "AI" in mode_text.upper() else "basic"

    gr.Info(f"开始处理 {len(uploaded_files)} 个文件，结果将实时展示。")
    latest_state = {"results": [], "choices": []}

    try:
        for event in process_ppt_files_stream(
            uploaded_files=uploaded_files,
            mode=mode_value,
            api_key=api_key.strip() or None,
            api_base=api_base.strip() or None,
            model=model.strip() or None,
            output_dir=output_dir.strip() or "./output_notes_web",
            overwrite=True,
            status_callback=None,
        ):
            summary = event["summary"]
            status_text = event.get("status_text", "处理中")
            progress_value = float(event.get("progress", 0.0) or 0.0)
            update_progress(progress_value, desc=status_text)

            results = summary.get("results", [])
            rows = _build_table_rows(results)
            choices = [_choice_label(i, item.get("file_name", f"file_{i+1}")) for i, item in enumerate(results)]
            active_idx = int(event.get("active_index", 0) or 0)
            default_choice = choices[active_idx] if 0 <= active_idx < len(choices) else (choices[0] if choices else None)
            latest_state = {"results": results, "choices": choices}

            selected_info, gallery_items, note_preview, note_file = _render_selected_file(default_choice, latest_state)
            status_md = _build_status_md(status_text, summary)

            yield (
                status_md,
                summary.get("logs", ""),
                rows,
                gr.update(choices=choices, value=default_choice),
                selected_info,
                gallery_items,
                note_preview,
                note_file,
                latest_state,
                [],
            )

        update_progress(1.0, desc="处理完成")
    except Exception as exc:  # noqa: BLE001
        update_progress(1.0, desc="处理失败")
        error_text = f"{type(exc).__name__}: {exc}"
        gr.Error(f"生成失败：{error_text}")
        failed_state = latest_state if latest_state.get("results") else {"results": [], "choices": []}
        yield (
            "### 处理状态\n- 状态：失败",
            f"生成过程异常：{error_text}",
            _build_table_rows(failed_state.get("results", [])),
            gr.update(choices=failed_state.get("choices", []), value=None),
            "暂无结果",
            [],
            "（生成失败）",
            None,
            failed_state,
            [],
        )


def on_select_file(choice: str, state: dict):
    selected_info, gallery_items, note_preview, note_file = _render_selected_file(
        choice, state or {"results": [], "choices": []}
    )
    return selected_info, gallery_items, note_preview, note_file, []


def on_mode_change(mode: str):
    show_ai = "AI" in (mode or "")
    return gr.update(visible=show_ai)


def clear_results():
    empty_state = {"results": [], "choices": []}
    return (
        "### 处理状态\n- 尚未开始",
        "",
        [],
        gr.update(choices=[], value=None),
        "暂无结果",
        [],
        "（正在等待生成内容）",
        None,
        empty_state,
        [],
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
        history.append((question, "请先开始处理 PPT，生成笔记后再提问。"))
        return history, None

    item = results[idx]
    current_note = item.get("note_preview", "")
    current_raw = item.get("raw_text_preview", "")
    if not (current_note or "").strip():
        history.append((question, "当前还没有可用笔记内容，请先等待至少一页生成完成。"))
        return history, None

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
            gr.Markdown("## NCWUStudyHub\n### 上传 PPT，实时生成学习笔记", elem_id="hero-title")
            with gr.Row():
                with gr.Column(scale=3, elem_classes=["ios-glass"], elem_id="control-panel"):
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
                    start_btn = gr.Button("开始处理", variant="primary", size="lg", elem_id="start-btn")
                    clear_result_btn = gr.Button("清空结果", variant="secondary")

                with gr.Column(scale=6, elem_classes=["ios-glass"], elem_id="note-panel"):
                    status_md = gr.Markdown("### 处理状态\n- 尚未开始", elem_id="status-pill")
                    file_picker = gr.Dropdown(label="文件", choices=[], value=None)
                    selected_info = gr.Markdown("暂无结果")
                    note_preview = gr.Markdown("（正在等待生成内容）", elem_id="workspace-note")
                    image_gallery = gr.Gallery(label="当前页相关图片", columns=2, height=260, type="filepath")
                    note_download = gr.File(label="下载 note.md")

                with gr.Column(scale=4, elem_classes=["ios-glass"], elem_id="assistant-panel"):
                    logs_box = gr.Textbox(label="处理日志", lines=9)
                    result_table = gr.Dataframe(
                        headers=["文件名", "模式", "状态", "页数", "图片数", "进度", "AI", "输出目录", "信息"],
                        datatype=["str", "str", "str", "number", "number", "str", "str", "str", "str"],
                        interactive=False,
                        label="结果总览",
                    )
                    chatbot = gr.Chatbot(label="学习助手", elem_id="chat-window")
                    chat_input = gr.Dropdown(
                        label="",
                        choices=[
                            "这份笔记的核心知识点是什么？",
                            "请按考试重点给我3分钟速记版",
                            "帮我按章节生成复习清单",
                            "请解释最难的三个概念并举例",
                        ],
                        value=None,
                        allow_custom_value=True,
                        elem_id="chat-question",
                    )
                    with gr.Row():
                        send_btn = gr.Button("发送", variant="primary")
                        clear_chat_btn = gr.Button("清空对话")

        mode_radio.change(fn=on_mode_change, inputs=[mode_radio], outputs=[ai_config_wrap])

        start_btn.click(
            fn=run_processing,
            inputs=[upload_files, mode_radio, api_key, api_base, model, output_dir],
            outputs=[
                status_md,
                logs_box,
                result_table,
                file_picker,
                selected_info,
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
            outputs=[selected_info, image_gallery, note_preview, note_download, chatbot],
        )

        clear_result_btn.click(
            fn=clear_results,
            outputs=[
                status_md,
                logs_box,
                result_table,
                file_picker,
                selected_info,
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
        clear_chat_btn.click(fn=clear_chat, outputs=[chatbot])

    return demo


if __name__ == "__main__":
    _patch_gradio_local_startup_request()
    app = build_ui()
    app.launch(server_name="127.0.0.1", server_port=7860, share=False, show_error=True)
