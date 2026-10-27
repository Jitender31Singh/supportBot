"""Bounded rolling transcript summary used alongside the most recent chat turns."""
from __future__ import annotations
from typing import Any


def _role(message: Any) -> str:
    message_type = getattr(message, 'type', None)
    if message_type in {'human', 'user'}:
        return 'USER'
    if message_type in {'ai', 'assistant'}:
        return 'ASSISTANT'
    if isinstance(message, dict):
        return {'user': 'USER', 'assistant': 'ASSISTANT'}.get(message.get('role'), 'SYSTEM')
    return 'SYSTEM'


def _content(message: Any) -> str:
    content = message.get('content', '') if isinstance(message, dict) else getattr(message, 'content', str(message))
    if not isinstance(content, str):
        content = str(content)
    return ' '.join(content.split())


def update_conversation_summary(
    messages: list[Any], previous_summary: str = '', summarized_count: int = 0,
    *, keep_recent: int = 15, max_chars: int = 1800,
) -> tuple[str, int]:
    """Summarize only newly old messages, leaving the last ``keep_recent`` untouched.

    This is a deterministic rolling transcript digest, not a model-generated fact store. Domain
    facts such as vehicle status and command results stay in typed session/workflow state.
    """
    count = len(messages)
    start = min(max(0, int(summarized_count or 0)), count)
    end = max(start, count - max(1, keep_recent))
    if end <= start:
        return previous_summary, start
    lines = []
    for message in messages[start:end]:
        content = _content(message)
        if not content:
            continue
        # Keep the digest readable and prevent one giant user paste from dominating memory.
        lines.append(f"{_role(message)}: {content[:220]}")
    if not lines:
        return previous_summary, end
    combined = '\n'.join(part for part in (previous_summary.strip(), '\n'.join(lines)) if part)
    return combined[-max_chars:], end
