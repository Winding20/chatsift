"""OpenAI 兼容的 AI 客户端。

任何提供 /chat/completions 的服务都能用：智谱、OpenAI、DeepSeek、本地 Ollama 等。
类名沿用 ZhipuAIClient，避免破坏已有导入。
"""

from __future__ import annotations

import json
from typing import Any

from openai import OpenAI

from app.config import get_ai_settings, get_ai_timeout


class ZhipuAIClient:
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
    ) -> None:
        settings = get_ai_settings()

        self.api_key = api_key or settings["api_key"]
        self.base_url = base_url or settings["base_url"]
        self.model = model or settings["model"]

        if not self.api_key:
            raise ValueError(
                "未配置 AI_API_KEY（旧版本变量名 ZHIPU_API_KEY 也可以）"
            )
        if not self.base_url:
            raise ValueError(
                "未配置 AI_BASE_URL（旧版本变量名 ZHIPU_BASE_URL 也可以）"
            )
        if not self.model:
            raise ValueError(
                "未配置 AI_MODEL（旧版本变量名 ZHIPU_MODEL 也可以）"
            )

        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=timeout or get_ai_timeout(),
        )

    def chat(self, prompt: str) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content or ""

    def chat_json(
        self,
        prompt: str,
        temperature: float | None = 0.2,
        max_tokens: int = 2600,
    ) -> dict[str, Any] | list[Any]:
        kwargs: dict[str, Any] = {"max_tokens": max_tokens}
        if temperature is not None:
            kwargs["temperature"] = temperature

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "请严格返回合法的 JSON 对象，"
                        "不要添加 Markdown 代码块或解释文字。"
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            **kwargs,
        )

        content = response.choices[0].message.content or ""

        try:
            result = json.loads(content)
        except json.JSONDecodeError as exc:
            repaired = repair_json(content)
            if repaired is None:
                raise ValueError("AI 返回的内容不是合法 JSON") from exc
            result = repaired

        if not isinstance(result, (dict, list)):
            raise ValueError("AI 返回的 JSON 顶层必须是对象或数组")

        return result



def repair_json(text: str) -> dict[str, Any] | list[Any] | None:
    """尽力修复被截断或包了代码块的 JSON；修不好返回 None。"""
    if not text:
        return None

    cleaned = text.strip()

    # 去掉 Markdown 代码块
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

    # 截取第一个 { 或 [ 到最后一个 } 或 ]
    start = min(
        (index for index in (cleaned.find("{"), cleaned.find("[")) if index >= 0),
        default=-1,
    )
    if start < 0:
        return None
    cleaned = cleaned[start:]

    end = max(cleaned.rfind("}"), cleaned.rfind("]"))
    if end > 0:
        cleaned = cleaned[: end + 1]

    for candidate in (cleaned, _close_brackets(cleaned)):
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, (dict, list)):
            return parsed

    return None


def _close_brackets(text: str) -> str:
    """给被截断的 JSON 补上缺失的右括号。"""
    stack: list[str] = []
    in_string = False
    escaped = False

    for char in text:
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char in "{[":
            stack.append(char)
        elif char in "}]" and stack:
            stack.pop()

    suffix = ""
    if in_string:
        suffix += '"'
    for opener in reversed(stack):
        suffix += "}" if opener == "{" else "]"

    return text + suffix


AIClient = ZhipuAIClient
