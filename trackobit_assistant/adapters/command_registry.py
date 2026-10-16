import re
from pathlib import Path
from typing import Any
import yaml
from trackobit_assistant.schemas.models import CommandSpec

def _normalize_key(s: str) -> str:
    return re.sub(r'[^a-z0-9]', '', s.lower())

class YamlCommandRegistry:
    def __init__(self, directory: Path):
        self.directory = Path(directory)
        self._registry: dict[str, list[CommandSpec]] = {}
        self._normalized_index: dict[str, list[CommandSpec]] = {}
        self._display_names: dict[str, str] = {}
        self._canonical_devices: list[str] = []
        self._configs: dict[str, dict[str, Any]] = {}
        self._specs: dict[str, dict[str, Any]] = {}
        self.reload()

    def reload(self) -> None:
        self._registry.clear()
        self._normalized_index.clear()
        self._display_names.clear()
        self._canonical_devices.clear()
        self._configs.clear()
        self._specs.clear()
        self.directory.mkdir(parents=True, exist_ok=True)
        for path in self.directory.glob('*.yaml'):
            raw = yaml.safe_load(path.read_text(encoding='utf-8')) or {}
            display_name = str(raw.get('device_type', path.stem)).strip()
            if display_name not in self._canonical_devices:
                self._canonical_devices.append(display_name)
            device_type = display_name.casefold()
            commands = [CommandSpec.model_validate(c) for c in raw.get('commands', [])]
            sorted_cmds = sorted(commands, key=lambda c: c.order)

            cfg = dict(raw.get('configuration') or raw.get('configurations') or {})
            if 'port' in raw:
                cfg['port'] = raw['port']

            for k in [device_type, path.stem.casefold()]:
                self._registry[k] = sorted_cmds
                self._normalized_index[_normalize_key(k)] = sorted_cmds
                self._display_names[k] = display_name
                self._configs[k] = cfg
                self._specs[k] = raw

            for alias in raw.get('aliases', []):
                alias_str = str(alias).strip()
                alias_k = alias_str.casefold()
                self._registry[alias_k] = sorted_cmds
                self._normalized_index[_normalize_key(alias_k)] = sorted_cmds
                if alias_k not in self._display_names:
                    self._display_names[alias_k] = alias_str
                self._configs[alias_k] = cfg
                self._specs[alias_k] = raw

    def get_commands(self, device_type: str) -> list[CommandSpec]:
        if not device_type:
            return []
        key = device_type.strip().casefold()
        if key in self._registry:
            return list(self._registry[key])
        norm = _normalize_key(key)
        if norm in self._normalized_index:
            return list(self._normalized_index[norm])
        # Fallback substring match
        for reg_key, cmds in self._normalized_index.items():
            if norm in reg_key or reg_key in norm:
                return list(cmds)
        return []

    def get_command(self, device_type: str, command_id: str) -> CommandSpec | None:
        return next((c for c in self.get_commands(device_type) if c.id == command_id), None)

    def get_configuration(self, device_type: str) -> dict[str, Any] | None:
        if not device_type:
            return None
        key = device_type.strip().casefold()
        if key in self._configs:
            return dict(self._configs[key])
        norm = _normalize_key(key)
        for k, cfg in self._configs.items():
            if _normalize_key(k) == norm:
                return dict(cfg)
        for k, cfg in self._configs.items():
            k_norm = _normalize_key(k)
            if norm in k_norm or k_norm in norm:
                return dict(cfg)
        return None

    def get_device_spec(self, device_type: str) -> dict[str, Any] | None:
        if not device_type:
            return None
        key = device_type.strip().casefold()
        if key in self._specs:
            return dict(self._specs[key])
        norm = _normalize_key(key)
        for k, spec in self._specs.items():
            if _normalize_key(k) == norm:
                return dict(spec)
        return None

    def get_display_name(self, device_type: str) -> str:
        key = device_type.strip().casefold()
        if key in self._display_names:
            return self._display_names[key]
        norm = _normalize_key(key)
        for k, v in self._display_names.items():
            if _normalize_key(k) == norm:
                return v
        return device_type

    def list_supported_devices(self) -> list[str]:
        return sorted(list(set(self._canonical_devices)))

    def find_device_in_text(self, text: str) -> str | None:
        if not text:
            return None
        text_lower = text.casefold()

        # Check against registered device names and aliases, longest first so "Concox V5" matches before "Concox"
        all_candidates = sorted(list(set(self._display_names.values())), key=lambda d: len(d), reverse=True)
        for dev in all_candidates:
            pattern = r'(?:\b|_)' + re.escape(dev.casefold()).replace(r'\ ', r'[\s_\-]+') + r'(?:\b|_)'
            if re.search(pattern, text_lower):
                return self.get_display_name(dev)

        # Check explicit device type pattern: e.g. "device type concox v5"
        match = re.search(r'(?:device\s+type|device|tracker)\s+([a-zA-Z0-9_\-]+(?:\s+[a-zA-Z0-9_\-]+)?)', text, re.IGNORECASE)
        if match:
            candidate = match.group(1).strip()
            norm = _normalize_key(candidate)
            if norm in self._normalized_index:
                return self.get_display_name(candidate)

        return None
