from __future__ import annotations

import time
from typing import Iterable

import requests

DEFAULT_PROMPT_TEMPLATE = """你是一名擅长整理大学课程资料的学习助手。
请把以下从 PPT 中提取出的原始内容，整理成适合大学生阅读和复习的 Markdown 学习笔记。

要求：
1. 不要编造原文没有的信息
2. 保留原有知识点
3. 把零散文字整理成清晰结构
4. 尽量按“主题/章节/知识点”组织
5. 对明显是标题、定义、公式、结论、步骤的内容进行分类整理
6. 输出要易读，不要只是机械转写
7. 如果某些内容残缺或难以判断，请明确标注“原文不清晰”
8. 不要省略重要术语
9. 输出语言为中文
10. 输出格式为 Markdown

输出结构建议：
# 标题
## 内容概览
## 详细笔记
## 关键概念
## 复习提纲
## 自测题"""


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
        model: str = "gpt-4o-mini",
        timeout: int = 120,
        retries: int = 3,
        retry_delay: float = 2.0,
        prompt_template: str = DEFAULT_PROMPT_TEMPLATE,
        logger=None,
    ) -> None:
        self.api_key = (api_key or "").strip()
        self.api_base = (api_base or "https://api.openai.com/v1").rstrip("/")
        self.model = (model or "gpt-4o-mini").strip()
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
                    "注意：仅在图片和知识点强相关时插图，不要机械堆图。\n\n"
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
        model=model or "gpt-4o-mini",
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
