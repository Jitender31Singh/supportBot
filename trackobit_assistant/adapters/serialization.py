from datetime import date, datetime
from typing import Any
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

def _value(value: Any) -> Any:
    if isinstance(value, datetime): return value.isoformat()
    if isinstance(value, date): return value.isoformat()
    if isinstance(value, dict): return {str(k): _value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)): return [_value(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None: return value
    return str(value)

def state_to_json(state: dict[str, Any]) -> dict[str, Any]:
    result = {}
    for key, val in state.items():
        if key == 'messages':
            msgs = []
            for msg in val or []:
                if isinstance(msg, HumanMessage): role = 'user'
                elif isinstance(msg, AIMessage): role = 'assistant'
                elif isinstance(msg, SystemMessage): role = 'system'
                elif isinstance(msg, ToolMessage): role = 'tool'
                else: role = 'assistant'
                content = msg.content if isinstance(msg.content, str) else str(msg.content)
                msgs.append({'id': msg.id or 'message-no-id', 'role': role, 'content': content})
            result[key] = msgs
        elif key != 'screenshot_path':
            result[key] = _value(val)
    # attach timestamps to transcript rows
    for row in result.get('messages', []):
        row.setdefault('created_at', datetime.now().astimezone().isoformat())
        row.setdefault('attachment_name', None)
    return result
