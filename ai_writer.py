from __future__ import annotations

import time

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

    def generate_note(self, doc_title: str, extracted_content_md: str) -> tuple[str | None, str | None]:
        if not self.is_available():
            return None, "AI 未启用：缺少 API Key 或 Base URL"

        endpoint = f"{self.api_base}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        user_prompt = (
            f"文档标题：{doc_title}\n\n"
            "以下是从 PPT 提取的结构化原始内容，请直接输出最终 Markdown 学习笔记。\n"
            "注意保留图片 Markdown 链接（images/...）。\n\n"
            f"{extracted_content_md}"
        )
        payload = {
            "model": self.model,
            "temperature": 0.2,
            "messages": [
                {"role": "system", "content": self.prompt_template},
                {"role": "user", "content": user_prompt},
            ],
        }

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
