from typing import Any
from trackobit_assistant.schemas.models import CommandSpec

def select_next_command(commands: list[CommandSpec], history: list[dict[str, Any]]) -> CommandSpec | None:
    executed = {item.get('command_id') for item in history}
    # Honor an explicit next_if_inconclusive preference from the previous command first.
    if history:
        prev = history[-1]
        next_ids = prev.get('next_if_inconclusive') or []
        for command_id in next_ids:
            if command_id not in executed:
                match = next((c for c in commands if c.id == command_id), None)
                if match: return match
    return next((command for command in sorted(commands, key=lambda c: c.order) if command.id not in executed), None)
