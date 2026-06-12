"""Context compression for long agent conversations.

Strategy:
- Token-based trigger (80% of context window)
- Direct LLM call to summarize old messages (no sub-agent overhead)
- Preserve: system prompt + recent N messages
- Fallback: rule-based truncation if LLM call fails
"""

from __future__ import annotations

import json
from typing import Any


def estimate_tokens(text: str) -> int:
    """Estimate token count. Conservative: mixed CJK/Latin."""
    if not text:
        return 0
    cjk = sum(1 for c in text if '一' <= c <= '鿿')
    other = len(text) - cjk
    return (cjk // 2) + (other // 4) + 1


def estimate_messages_tokens(messages: list[dict[str, Any]]) -> int:
    """Estimate total tokens in a message list."""
    total = 0
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            total += estimate_tokens(content)
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict):
                    total += estimate_tokens(part.get("text", ""))
        for tc in msg.get("tool_calls", []):
            total += estimate_tokens(json.dumps(tc, ensure_ascii=False))
    return total


def should_compress(messages: list[dict[str, Any]], limit: int = 200_000) -> bool:
    """Check if messages exceed token threshold."""
    return estimate_messages_tokens(messages) > limit


def _drop_redundant(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop redundant messages (self-check prompts, VERIFIED)."""
    result = []
    for msg in messages:
        role = msg.get("role", "")
        content = str(msg.get("content", ""))
        if role == "user" and ("自检" in content or "请输出最终答案" in content):
            continue
        if role == "assistant" and content.strip().upper() == "VERIFIED":
            continue
        result.append(msg)
    return result


def _truncate_messages(messages: list[dict[str, Any]], max_chars: int = 300) -> list[dict[str, Any]]:
    """Rule-based fallback: truncate long messages."""
    result = []
    for msg in messages:
        role = msg.get("role", "")
        content = str(msg.get("content", ""))
        if role == "tool" and len(content) > max_chars:
            msg = {**msg, "content": content[:max_chars] + "\n...[truncated]"}
        elif role == "assistant" and len(content) > max_chars * 2:
            msg = {**msg, "content": content[:max_chars * 2] + "\n...[truncated]"}
        result.append(msg)
    return result


async def compress_messages(
    messages: list[dict[str, Any]],
    *,
    keep_recent: int = 6,
    target_tokens: int = 150_000,
    client: Any = None,
) -> list[dict[str, Any]]:
    """Compress message history.

    If client is provided, uses direct LLM call for summarization.
    Otherwise falls back to rule-based truncation.

    Args:
        messages: Full message history
        keep_recent: Number of recent messages to keep intact
        target_tokens: Target token count after compression
        client: ChatCompletionClient for LLM-based compression
    """
    if len(messages) <= keep_recent + 1:
        return messages

    system = messages[0]
    old_messages = messages[1:-keep_recent]
    recent_messages = messages[-keep_recent:]

    # Drop redundant
    old_messages = _drop_redundant(old_messages)
    if not old_messages:
        return [system] + recent_messages

    # Try LLM-based compression
    if client is not None:
        try:
            summary = await _llm_compress(old_messages, client)
            if summary:
                summary_msg = {
                    "role": "user",
                    "content": f"[Context Summary - compressed from {len(old_messages)} messages]\n{summary}",
                }
                return [system, summary_msg] + recent_messages
        except Exception:
            pass  # Fall through to rule-based

    # Fallback: rule-based truncation
    compressed = _truncate_messages(old_messages)
    result = [system] + compressed + recent_messages

    # If still too long, summarize oldest half
    if estimate_messages_tokens(result) > target_tokens and len(compressed) > 4:
        mid = len(compressed) // 2
        first_half = compressed[:mid]
        second_half = compressed[mid:]

        parts = []
        for msg in first_half:
            role = msg.get("role", "")
            content = str(msg.get("content", ""))[:100]
            if role == "tool":
                parts.append(f"[{msg.get('name', 'tool')}] {content}")
            elif role == "assistant" and content:
                parts.append(f"[assistant] {content}")

        summary_msg = {
            "role": "user",
            "content": "[Context Summary]\n" + "\n".join(parts[-10:]),
        }
        result = [system, summary_msg] + second_half + recent_messages

    return result


async def _llm_compress(
    messages: list[dict[str, Any]],
    client: Any,
) -> str | None:
    """Direct LLM call to summarize old messages."""
    # Format messages into readable text
    formatted = []
    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")
        name = msg.get("name", "")

        if isinstance(content, list):
            content = "[multimodal]"
        elif not isinstance(content, str):
            content = str(content)

        if len(content) > 400:
            content = content[:400] + "..."

        prefix = f"[{role}:{name}]" if name else f"[{role}]"
        formatted.append(f"{prefix} {content}")

    conversation = "\n".join(formatted)

    # Make a lightweight LLM call
    compress_messages_list = [
        {
            "role": "user",
            "content": (
                "请将以下对话历史压缩为简洁摘要。保留关键事实、数据和决策，丢弃工具调用细节和重复内容。\n"
                "用 3-5 个要点概括，每个要点一行。直接输出摘要，不要解释。\n\n"
                f"{conversation}"
            ),
        }
    ]

    from source.runtime.openai_chat_client import first_message
    completion = await client.create(
        messages=compress_messages_list,
        tools=[],
        tool_choice="none",
    )
    content = str(first_message(completion).get("content") or "").strip()
    return content if content else None
