"""Context compression for long agent conversations.

Strategies inspired by LangGraph, Claude Code, and Deep Agents:
- Token-based trigger (80% of context window)
- Preserve: system prompt, recent messages, tool results with answers
- Compress: older tool results → summaries, old conversation → key points
- Never compress aggressively — minimize information loss
"""

from __future__ import annotations

import json
import re
from typing import Any


# Approximate token count: Chinese ≈ 2 chars/token, English ≈ 4 chars/token
def estimate_tokens(text: str) -> int:
    """Estimate token count from text. Conservative: assumes mixed CJK/Latin."""
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
        # Tool calls overhead
        for tc in msg.get("tool_calls", []):
            total += estimate_tokens(json.dumps(tc, ensure_ascii=False))
    return total


def should_compress(messages: list[dict[str, Any]], limit: int = 200_000) -> bool:
    """Check if messages exceed token threshold."""
    return estimate_messages_tokens(messages) > limit


def compress_messages(
    messages: list[dict[str, Any]],
    *,
    keep_recent: int = 6,
    target_tokens: int = 150_000,
) -> list[dict[str, Any]]:
    """Compress message history while preserving key information.

    Strategy:
    1. Always keep: system prompt (first message) + recent messages
    2. Compress: older tool results (keep only tool_name + first 200 chars)
    3. Compress: older assistant messages (keep first 300 chars)
    4. Drop: old user prompts that are just "自检" or "请输出最终答案"

    Args:
        messages: Full message history
        keep_recent: Number of recent messages to keep intact
        target_tokens: Target token count after compression
    """
    if len(messages) <= keep_recent + 1:
        return messages

    # Split: system prompt + old + recent
    system = messages[0]
    old_messages = messages[1:-keep_recent]
    recent_messages = messages[-keep_recent:]

    # Phase 1: Drop redundant messages
    compressed_old = []
    for msg in old_messages:
        role = msg.get("role", "")
        content = str(msg.get("content", ""))

        # Drop self-check prompts
        if role == "user" and ("自检" in content or "请输出最终答案" in content):
            continue

        # Drop VERIFIED responses
        if role == "assistant" and content.strip().upper() == "VERIFIED":
            continue

        compressed_old.append(msg)

    # Phase 2: Compress old tool results
    further_compressed = []
    for msg in compressed_old:
        role = msg.get("role", "")

        if role == "tool":
            # Compress tool results: keep tool name + first 200 chars
            content = str(msg.get("content", ""))
            if len(content) > 300:
                msg = {**msg, "content": content[:200] + "\n...[compressed]"}
            further_compressed.append(msg)

        elif role == "assistant":
            # Compress old assistant messages: keep first 300 chars
            content = str(msg.get("content", ""))
            if len(content) > 500:
                msg = {**msg, "content": content[:300] + "\n...[compressed]"}
            # Keep tool_calls metadata
            further_compressed.append(msg)

        else:
            further_compressed.append(msg)

    result = [system] + further_compressed + recent_messages

    # Phase 3: If still too aggressive, do one more round on the oldest half
    if estimate_messages_tokens(result) > target_tokens and len(further_compressed) > 4:
        mid = len(further_compressed) // 2
        first_half = further_compressed[:mid]
        second_half = further_compressed[mid:]

        # Summarize first half into a single message
        summary_parts = []
        for msg in first_half:
            role = msg.get("role", "")
            content = str(msg.get("content", ""))[:100]
            if role == "tool":
                tool_name = msg.get("name", "unknown")
                summary_parts.append(f"[tool:{tool_name}] {content}")
            elif role == "assistant" and content:
                summary_parts.append(f"[assistant] {content}")

        summary_msg = {
            "role": "user",
            "content": "[Context Summary]\n" + "\n".join(summary_parts[-10:]),
        }

        result = [system, summary_msg] + second_half + recent_messages

    return result
