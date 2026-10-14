from pathlib import Path
import yaml
from trackobit_assistant.schemas.models import CommandSpec

class YamlCommandRegistry:
    def __init__(self, directory: Path):
        self.directory = Path(directory)
        self._registry: dict[str, list[CommandSpec]] = {}
        self.reload()
    def reload(self) -> None:
        self._registry.clear()
        self.directory.mkdir(parents=True, exist_ok=True)
        for path in self.directory.glob('*.yaml'):
            raw = yaml.safe_load(path.read_text(encoding='utf-8')) or {}
            device_type = str(raw.get('device_type', path.stem)).strip().casefold()
            commands = [CommandSpec.model_validate(c) for c in raw.get('commands', [])]
            self._registry[device_type] = sorted(commands, key=lambda c: c.order)
    def get_commands(self, device_type: str) -> list[CommandSpec]:
        key = device_type.strip().casefold()
        return list(self._registry.get(key, []))
    def get_command(self, device_type: str, command_id: str) -> CommandSpec | None:
        return next((c for c in self.get_commands(device_type) if c.id == command_id), None)
