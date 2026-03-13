from __future__ import annotations

import time
from typing import Iterable

import requests

DEFAULT_PROMPT_TEMPLATE = """Note Organization Guidelines

Core Rules (for AI)
1. RULE_BOLD_KEYWORDS: Use **bold** for key concepts or conclusions in the main text for quick scanning.
2. RULE_CODE_REMOVE_PROMPT: Remove any >>> prefixes before code.
3. RULE_CODE_BLOCKS: Format code in clean, readable code blocks.
4. RULE_NO_CONTENT_CHANGE: If no content changes are requested, only adjust formatting and layout.
5. RULE_REMOVE_COPY_LABEL: Remove labels like 澶嶅埗浠ｇ爜.
6. RULE_REMOVE_SOURCE_LABEL_PRECISE: Remove explicit source/copyright label text (for example 鏉ユ簮浜巂銆乣鏉ヨ嚜銆乣鐗堟潈灞炰簬銆乣Powered by and similar labels). Also remove the plain root-domain link https://fishc.com.cn (including equivalent root forms like https://fishc.com.cn/). Keep specific FishC page links (for example https://fishc.com.cn/thread-xxxxxx-1-1.html) and other normal reference/external links.
7. RULE_TMP_FILES_CLEANUP: Temporary files are allowed during work, but they must be deleted after the task is completed.
8. RULE_NO_PARAPHRASE_UNLESS_SUMMARIZE: If you did not explicitly ask for a summary, do not paraphrase, rewrite, shorten, or alter your original wording; keep your original text unchanged.
9. RULE_KEEP_EXPLANATION_VERBATIM: Do not change the user's explanation sections. Preserve explanation content, level of detail, and length. You may only fix encoding/formatting issues (for example mojibake cleanup, code fences, spacing) without changing meaning or reducing detail.
10. RULE_CODE_BLOCK_LANGUAGE_AND_COVERAGE: Do not convert all code blocks to text; use the correct language tag by content (for example python for Python code, bash for command line). Any code snippet must be wrapped in a fenced code block and must not be left unframed.

Math Formula Guidelines
1. MATH_DELIMITERS_INLINE: Use $...$ for short variables or symbols.
2. MATH_DELIMITERS_BLOCK: Use $$...$$ for full equations or anything that should look book-style.
3. MATH_BOOK_FRACTIONS: Replace 1/(1+x^2) with \frac{1}{1+x^2}.
4. MATH_BOOK_ROOTS: Replace sqrt(...) with \sqrt{...}.
5. MATH_BOOK_INTEGRALS: Replace 鈭玚 with \int.
6. MATH_BOOK_TRIG_LOG: Replace sin, cos, tan, sec, ln, arctan with \sin, \cos, \tan, \sec, \ln, \arctan.
7. MATH_BOOK_POWERS: Replace x^(n+1) with x^{n+1}.
8. MATH_MODE_TEXT: Wrap variables and formulas in $...$ inside text.
9. MATH_BLOCK_DEFAULT: If a line is mainly a formula, use $$...$$ (inline only for short, simple symbols).

Encoding Note
1. ENCODING_CAUSE: Reading the file with the wrong encoding (e.g., treating UTF-8 as GBK/ANSI) causes mojibake.
2. ENCODING_FIX: Rewrite the file with the correct encoding (UTF-8).
3. ENCODING_SAFE_WRITE: When editing files, preserve UTF-8 encoding and avoid unsafe overwrite methods that can cause encoding drift/mojibake.

Output language: Chinese.
Output format: Markdown."""


def _clip_text(text: str, limit: int) -> str:
    text = text or ""
    if len(text) <= limit:
        return text
    return text[:limit] + "\n\n[内容过长，已截断]"


def _history_to_messages(history: Iterable[tuple[str, str]], max_rounds: int = 6) -> list[dict]:
    history_list = list(history)
    if max_rounds > 0:
        history_list = history_list[-max_rounds:]
    messages: list[dict] = []
    for user_text, assistant_text in history_list:
        if user_text:
            messages.append({"role": "user", "content": user_text})
        if assistant_text:
            messages.append({"role": "assistant", "content": assistant_text})
    return messages


class AIWriter:
    def __init__(
        self,
        api_key: str | None,
        api_base: str | None,
        model: str = "deepseek-chat",
        timeout: int = 120,
        retries: int = 3,
        retry_delay: float = 2.0,
        prompt_template: str = DEFAULT_PROMPT_TEMPLATE,
        logger=None,
    ) -> None:
        self.api_key = (api_key or "").strip()
        self.api_base = (api_base or "https://api.deepseek.com/v1").rstrip("/")
        self.model = (model or "deepseek-chat").strip()
        self.timeout = timeout
        self.retries = retries
        self.retry_delay = retry_delay
        self.prompt_template = prompt_template
        self.logger = logger

    def is_available(self) -> bool:
        return bool(self.api_key and self.api_base and self.model)

    def _chat_completion(self, messages: list[dict], temperature: float = 0.2) -> tuple[str | None, str | None]:
        if not self.is_available():
            return None, "AI 未启用：缺少 API Key 或 Base URL"

        endpoint = f"{self.api_base}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {"model": self.model, "temperature": temperature, "messages": messages}

        last_error = None
        for attempt in range(1, self.retries + 1):
            try:
                response = requests.post(endpoint, headers=headers, json=payload, timeout=self.timeout)
                if response.status_code >= 400:
                    err_text = response.text[:600]
                    raise RuntimeError(f"HTTP {response.status_code}: {err_text}")
                data = response.json()
                content = data["choices"][0]["message"]["content"].strip()
                if not content:
                    raise RuntimeError("AI 返回内容为空")
                return content, None
            except Exception as exc:  # noqa: BLE001
                last_error = str(exc)
                if self.logger:
                    self.logger.warning("AI 调用失败(%s/%s): %s", attempt, self.retries, last_error)
                if attempt < self.retries:
                    time.sleep(self.retry_delay * attempt)
        return None, f"AI 调用失败：{last_error}"

    def generate_note(self, doc_title: str, extracted_content_md: str) -> tuple[str | None, str | None]:
        messages = [
            {"role": "system", "content": self.prompt_template},
            {
                "role": "user",
                "content": (
                    f"文档标题：{doc_title}\n\n"
                    "以下是从 PPT 提取的结构化原始内容，请直接输出最终 Markdown 学习笔记。\n"
                    "注意：严格遵循 Note Organization Guidelines、Math Formula Guidelines 和 Encoding Note。\n"
                    "可图文混排，但仅在图片和知识点强相关时插图，不要机械堆图。\n\n"
                    f"{extracted_content_md}"
                ),
            },
        ]
        return self._chat_completion(messages=messages, temperature=0.2)


def chat_with_note(
    user_message: str,
    current_note_markdown: str,
    current_raw_text: str | None = None,
    api_key: str | None = None,
    api_base: str | None = None,
    model: str | None = None,
    history: list[tuple[str, str]] | None = None,
) -> tuple[str | None, str | None]:
    """
    基于当前生成笔记进行问答。
    返回：(assistant_reply, error)
    """
    user_message = (user_message or "").strip()
    if not user_message:
        return None, "请输入问题"

    if not (current_note_markdown or "").strip():
        return None, "请先上传并处理 PPT，再进行提问"

    writer = AIWriter(
        api_key=api_key,
        api_base=api_base,
        model=model or "deepseek-chat",
    )
    if not writer.is_available():
        return None, "当前未配置 AI 对话能力"

    note_context = _clip_text(current_note_markdown, 16000)
    raw_context = _clip_text(current_raw_text or "", 8000)

    system_prompt = (
        "你是学习资料问答助手。回答必须严格基于“当前笔记内容”和“原始提取内容”。\n"
        "规则：\n"
        "1) 不要编造资料中没有的信息。\n"
        "2) 优先引用笔记中的章节和要点。\n"
        "3) 若资料不足，请明确说“当前资料中没有足够信息”。\n"
        "4) 输出中文，结构清晰，简洁。"
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": (
                "下面是当前问答上下文，请据此回答后续问题。\n\n"
                f"## 当前笔记\n{note_context}\n\n"
                f"## 原始提取（辅助）\n{raw_context or '无'}"
            ),
        },
    ]
    messages.extend(_history_to_messages(history or [], max_rounds=6))
    messages.append({"role": "user", "content": user_message})
    return writer._chat_completion(messages=messages, temperature=0.2)
