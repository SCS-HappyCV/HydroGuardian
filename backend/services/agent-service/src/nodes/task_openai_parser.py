from __future__ import annotations

import json
from typing import Any, Dict
from urllib.parse import urlparse

# OpenAI-compatible 工具调用解析逻辑。

from config import (
    TASK_PARSER_OPENAI_API_KEY,
    TASK_PARSER_OPENAI_BASE_URL,
    TASK_PARSER_OPENAI_DISABLE_THINKING,
    TASK_PARSER_OPENAI_MAX_TOKENS,
    TASK_PARSER_OPENAI_MODEL,
    TASK_PARSER_OPENAI_ORGANIZATION,
    TASK_PARSER_OPENAI_PROJECT,
    TASK_PARSER_OPENAI_TIMEOUT_SECONDS,
)
from state import AgentState

from .task_contract import SYSTEM_PROMPT, TASK_PARSE_TOOL, normalize_intent


_openai_client: Any | None = None


def _is_local_openai_base_url(base_url: str) -> bool:
    if not base_url:
        return False
    try:
        host = urlparse(base_url).hostname or ""
    except Exception:
        return False
    return host in {"localhost", "127.0.0.1", "0.0.0.0"} or host.startswith("192.168.")


def _normalize_openai_base_url(base_url: str) -> str:
    value = base_url.rstrip("/")
    for suffix in ("/chat/completions", "/responses", "/completions"):
        if value.endswith(suffix):
            return value[: -len(suffix)]
    return value


def _get_openai_client():
    global _openai_client
    if _openai_client is not None:
        return _openai_client

    try:
        from openai import AsyncOpenAI
    except Exception as exc:
        raise ImportError("任务理解 LLM 需要安装 openai Python 包。") from exc

    api_key = TASK_PARSER_OPENAI_API_KEY
    if not api_key and _is_local_openai_base_url(TASK_PARSER_OPENAI_BASE_URL):
        api_key = "EMPTY"
    if not api_key:
        raise EnvironmentError("缺少 OPENAI_API_KEY 或 AGENT_TASK_PARSER_OPENAI_API_KEY。")

    kwargs: Dict[str, Any] = {
        "api_key": api_key,
        "timeout": TASK_PARSER_OPENAI_TIMEOUT_SECONDS,
    }
    if TASK_PARSER_OPENAI_BASE_URL:
        kwargs["base_url"] = _normalize_openai_base_url(TASK_PARSER_OPENAI_BASE_URL)
    if TASK_PARSER_OPENAI_ORGANIZATION:
        kwargs["organization"] = TASK_PARSER_OPENAI_ORGANIZATION
    if TASK_PARSER_OPENAI_PROJECT:
        kwargs["project"] = TASK_PARSER_OPENAI_PROJECT

    _openai_client = AsyncOpenAI(**kwargs)
    return _openai_client


def _build_user_prompt(state: AgentState) -> str:
    return (
        f"scene_id: {state['scene_id'] or '(missing)'}\n"
        f"sample_id: {state['sample_id'] or '(missing)'}\n"
        f"user_task: {state['task_text'].strip()}"
    )


def _parse_payload_text(text: str) -> Dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()
    try:
        payload = json.loads(cleaned)
    except Exception:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start < 0 or end <= start:
            raise
        payload = json.loads(cleaned[start : end + 1])
    if not isinstance(payload, dict):
        raise TypeError("任务解析响应必须是 JSON object。")
    return payload


def _extract_tool_payload(response: Any) -> Dict[str, Any]:
    choices = getattr(response, "choices", None) or []
    if not choices:
        raise ValueError("OpenAI 任务解析响应没有 choices。")
    message = getattr(choices[0], "message", None)
    if message is None:
        raise ValueError("OpenAI 任务解析响应没有 message。")

    tool_calls = getattr(message, "tool_calls", None) or []
    if tool_calls:
        tool_call = tool_calls[0]
        function = getattr(tool_call, "function", None)
        arguments = getattr(function, "arguments", None) if function is not None else None
        if not arguments and isinstance(tool_call, dict):
            arguments = tool_call.get("function", {}).get("arguments")
        if not arguments:
            raise ValueError("OpenAI 工具调用没有返回 arguments。")
        return _parse_payload_text(str(arguments))

    content = getattr(message, "content", "") or ""
    if isinstance(content, list):
        content = "".join(str(part.get("text", part)) for part in content)
    return _parse_payload_text(str(content))


async def parse_task_with_llm(state: AgentState) -> Dict[str, Any]:
    client = _get_openai_client()
    request_kwargs: Dict[str, Any] = {
        "model": TASK_PARSER_OPENAI_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _build_user_prompt(state)},
        ],
        "tools": [TASK_PARSE_TOOL],
        "tool_choice": {"type": "function", "function": {"name": "parse_hydro_task"}},
        "temperature": 0.0,
        "max_tokens": TASK_PARSER_OPENAI_MAX_TOKENS,
    }
    if TASK_PARSER_OPENAI_DISABLE_THINKING:
        request_kwargs["extra_body"] = {
            "chat_template_kwargs": {"enable_thinking": False},
        }

    response = await client.chat.completions.create(**request_kwargs)
    payload = _extract_tool_payload(response)
    return normalize_intent(payload, state, parser_source="openai_tool")
