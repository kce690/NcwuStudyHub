from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote

import gradio as gr
from dotenv import load_dotenv

from ai_writer import chat_with_note
from processor import process_ppt_files_stream

IMG_PATTERN = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")


def _clean_text(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


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


def _choice_label(index: int, file_name: str) -> str:
    return f"{index + 1}. {file_name}"


def _get_selected_index(choice: str | None, state: dict) -> int:
    choices = state.get("choices", [])
    if not choices:
        return -1
    if choice in choices:
        return choices.index(choice)
    return 0


def _render_note_for_web(note_markdown: str, output_dir: str) -> str:
    note_markdown = note_markdown or ""
    if not note_markdown.strip():
        return "（正在整理笔记...）"

    root = Path(output_dir) if output_dir else None

    def _replace(match: re.Match[str]) -> str:
        alt = match.group(1)
        path_text = (match.group(2) or "").strip()
        if not path_text:
            return match.group(0)
        lowered = path_text.lower()
        if lowered.startswith(("http://", "https://", "data:", "/gradio_api/file=")):
            return match.group(0)

        img_path = Path(path_text)
        if not img_path.is_absolute():
            if not root:
                return match.group(0)
            img_path = root / img_path
        if not img_path.exists():
            return match.group(0)

        web_path = quote(str(img_path).replace("\\", "/"), safe="/:._-()")
        return f"![{alt}](/gradio_api/file={web_path})"

    return IMG_PATTERN.sub(_replace, note_markdown)


def _render_selected_file(choice: str | None, state: dict):
    results = state.get("results", [])
    idx = _get_selected_index(choice, state)
    if idx < 0 or idx >= len(results):
        return "## 笔记", "（暂无可阅读笔记）", None, "若未配置 API Key，AI 对话会提示不可用。"

    item = results[idx]
    file_name = item.get("file_name", "")
    note_preview = item.get("note_preview", "") or ""
    output_dir = item.get("output_dir", "")
    if not note_preview.strip() and item.get("error"):
        note_web = f"该文件生成失败：{item.get('error')}"
    else:
        note_web = _render_note_for_web(note_preview, output_dir)
    note_file = item.get("note_path") or None
    if note_file and not Path(str(note_file)).exists():
        note_file = None

    ai_hint = "AI 对话基于当前笔记内容。若未配置 API Key，会提示不可用。"
    return f"## {file_name}", note_web, note_file, ai_hint


def _extract_message_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(str(item.get("text", "")))
        return "\n".join([x for x in parts if x])
    return str(content or "")


def _history_to_pairs(history_messages: list[dict] | None) -> list[tuple[str, str]]:
    history_messages = history_messages or []
    pairs: list[tuple[str, str]] = []
    pending_user = ""
    for msg in history_messages:
        role = msg.get("role")
        text = _extract_message_text(msg.get("content"))
        if role == "user":
            pending_user = text
        elif role == "assistant":
            pairs.append((pending_user, text))
            pending_user = ""
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
    progress_fn = progress if callable(progress) else None

    def update_progress(fraction: float) -> None:
        if progress_fn:
            progress_fn(max(0.0, min(fraction, 1.0)), desc="正在整理笔记...")

    if not uploaded_files:
        gr.Warning("请先上传至少一个 .pptx 文件。")
        empty_state = {"results": [], "choices": []}
        yield (
            gr.update(choices=[], value=None, visible=False),
            "## 笔记",
            "（暂无可阅读笔记）",
            None,
            empty_state,
            [],
            gr.update(visible=True),
            gr.update(visible=False),
            gr.update(visible=False, value=""),
            "未配置 AI Key 时，对话将不可用。",
        )
        return

    mode_value = "ai" if "AI" in (mode or "").upper() else "basic"
    update_progress(0.0)
    placeholder_state = {"results": [], "choices": []}
    yield (
        gr.update(choices=[], value=None, visible=False),
        "## 笔记",
        "正在整理笔记...",
        None,
        placeholder_state,
        [],
        gr.update(visible=False),
        gr.update(visible=True),
        gr.update(visible=True, value="正在整理笔记..."),
        "AI 对话将基于生成后的笔记。",
    )

    try:
        last_event = None
        for event in process_ppt_files_stream(
            uploaded_files=uploaded_files,
            mode=mode_value,
            api_key=_clean_text(api_key) or None,
            api_base=_clean_text(api_base) or None,
            model=_clean_text(model) or None,
            output_dir=_clean_text(output_dir) or "./output_notes_web",
            overwrite=True,
            status_callback=None,
        ):
            last_event = event
            update_progress(float(event.get("progress", 0.0) or 0.0))

        if not last_event:
            raise RuntimeError("未获得处理结果")

        summary = last_event["summary"]
        results = summary.get("results", [])
        choices = [_choice_label(i, item.get("file_name", f"file_{i+1}")) for i, item in enumerate(results)]
        state = {"results": results, "choices": choices}
        default_choice = choices[0] if choices else None
        note_title, note_preview, note_file, ai_hint = _render_selected_file(default_choice, state)

        yield (
            gr.update(choices=choices, value=default_choice, visible=len(choices) > 1),
            note_title,
            note_preview,
            note_file,
            state,
            [],
            gr.update(visible=False),
            gr.update(visible=True),
            gr.update(visible=False, value=""),
            ai_hint,
        )
        update_progress(1.0)
    except Exception as exc:  # noqa: BLE001
        error_text = f"{type(exc).__name__}: {exc}"
        gr.Error(f"生成失败：{error_text}")
        yield (
            gr.update(choices=[], value=None, visible=False),
            "## 笔记",
            f"生成失败：{error_text}",
            None,
            placeholder_state,
            [],
            gr.update(visible=False),
            gr.update(visible=True),
            gr.update(visible=False, value=""),
            "未配置 AI Key 时，对话将不可用。",
        )


def on_select_file(choice: str, state: dict):
    note_title, note_preview, note_file, ai_hint = _render_selected_file(choice, state or {"results": [], "choices": []})
    return note_title, note_preview, note_file, [], ai_hint


def on_mode_change(mode: str):
    show_ai = "AI" in (mode or "")
    return gr.update(visible=show_ai)


def back_to_upload():
    empty_state = {"results": [], "choices": []}
    return (
        gr.update(choices=[], value=None, visible=False),
        "## 笔记",
        "（暂无可阅读笔记）",
        None,
        empty_state,
        [],
        gr.update(visible=True),
        gr.update(visible=False),
        gr.update(visible=False, value=""),
        "未配置 AI Key 时，对话将不可用。",
    )


def clear_chat():
    return []


def chat_submit(
    user_message: str | None,
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
        history.append({"role": "assistant", "content": "请先完成一次笔记生成。"})
        return history, ""

    item = results[idx]
    current_note = item.get("note_preview", "")
    current_raw = item.get("raw_text_preview", "")
    if not (current_note or "").strip():
        history.append({"role": "user", "content": question})
        history.append({"role": "assistant", "content": "当前还没有可用笔记内容，请稍后再问。"})
        return history, ""

    reply, err = chat_with_note(
        user_message=question,
        current_note_markdown=current_note,
        current_raw_text=current_raw,
        api_key=_clean_text(api_key) or os.getenv("DEEPSEEK_API_KEY"),
        api_base=_clean_text(api_base) or os.getenv("DEEPSEEK_BASE_URL"),
        model=_clean_text(model) or os.getenv("DEEPSEEK_MODEL"),
        history=_history_to_pairs(history),
    )

    history.append({"role": "user", "content": question})
    history.append({"role": "assistant", "content": reply if reply else err or "当前资料中没有足够信息"})
    return history, ""


def build_ui() -> gr.Blocks:
    load_dotenv()
    default_api_base = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
    default_model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

    with gr.Blocks(title="NCWUStudyHub", fill_width=True) as demo:
        state = gr.State({"results": [], "choices": []})
        gr.HTML(f"<style>{_load_ios_css()}</style>")
        gr.HTML(f"<script>{_load_ios_js()}</script>")

        with gr.Column(elem_id="app-shell"):
            with gr.Column(elem_id="upload-screen", visible=True) as upload_screen:
                with gr.Column(elem_classes=["ios-glass", "upload-card"]):
                    gr.Markdown("# NCWUStudyHub", elem_id="hero-title")
                    gr.Markdown("上传 PPT，自动整理为便于复习的学习笔记", elem_id="hero-subtitle")
                    upload_files = gr.File(
                        label="上传 .pptx 文件（可多选）",
                        file_count="multiple",
                        file_types=[".pptx"],
                        type="filepath",
                    )
                    mode_radio = gr.Radio(label="处理模式", choices=["普通模式", "AI 增强模式"], value="普通模式")
                    with gr.Column(visible=False) as ai_config_wrap:
                        with gr.Accordion("AI 配置（仅 AI 增强模式使用）", open=False):
                            api_key = gr.Textbox(label="DeepSeek API Key", type="password")
                            api_base = gr.Textbox(label="DeepSeek Base URL", value=default_api_base)
                            model = gr.Textbox(label="DeepSeek Model", value=default_model)
                    output_dir = gr.Textbox(label="输出目录", value="./output_notes_web")
                    start_btn = gr.Button("开始处理", variant="primary", size="lg", elem_id="start-btn")

            with gr.Column(elem_id="reading-screen", visible=False) as reading_screen:
                with gr.Row(elem_id="reading-top-row"):
                    new_task_btn = gr.Button("返回上传", variant="secondary")
                    file_picker = gr.Dropdown(label="文件切换", choices=[], value=None, visible=False)

                processing_hint = gr.Markdown("正在整理笔记...", visible=False, elem_id="processing-hint")

                with gr.Row(elem_id="reading-layout"):
                    with gr.Column(scale=9, elem_classes=["ios-glass", "note-reader"]):
                        note_title = gr.Markdown("## 笔记")
                        note_preview = gr.Markdown("（暂无可阅读笔记）", elem_id="workspace-note")
                        note_download = gr.File(label="下载 note.md")
                    with gr.Column(scale=3, elem_classes=["ios-glass", "ai-sidebar"]):
                        ai_hint = gr.Markdown("未配置 AI Key 时，对话将不可用。", elem_id="ai-hint")
                        chatbot = gr.Chatbot(label="AI 问答", elem_id="chat-window")
                        chat_input = gr.Textbox(label="", placeholder="基于当前笔记提问", elem_id="chat-question")
                        with gr.Row():
                            send_btn = gr.Button("发送", variant="primary")
                            clear_chat_btn = gr.Button("清空")

        mode_radio.change(fn=on_mode_change, inputs=[mode_radio], outputs=[ai_config_wrap])

        start_btn.click(
            fn=run_processing,
            inputs=[upload_files, mode_radio, api_key, api_base, model, output_dir],
            outputs=[
                file_picker,
                note_title,
                note_preview,
                note_download,
                state,
                chatbot,
                upload_screen,
                reading_screen,
                processing_hint,
                ai_hint,
            ],
        )

        file_picker.change(
            fn=on_select_file,
            inputs=[file_picker, state],
            outputs=[note_title, note_preview, note_download, chatbot, ai_hint],
        )

        new_task_btn.click(
            fn=back_to_upload,
            outputs=[
                file_picker,
                note_title,
                note_preview,
                note_download,
                state,
                chatbot,
                upload_screen,
                reading_screen,
                processing_hint,
                ai_hint,
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
