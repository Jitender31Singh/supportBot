from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


def _normalize_key(s: str) -> str:
    """Normalize string for robust key lookup (lowercase, alphanumeric only)."""
    return re.sub(r"[^a-z0-9]", "", s.lower())


@dataclass(frozen=True)
class DevicePortInfo:
    enum_name: str
    code: str
    display_name: str
    expected_port: str


class DevicePortRegistry:
    """Registry mapping 200+ hardware device models to their expected communication ports."""

    def __init__(self, mapping_path: Optional[Path] = None):
        if mapping_path is None:
            # Default to config/device_port_mapping.json
            mapping_path = Path(__file__).resolve().parents[2] / "config" / "device_port_mapping.json"
        self.mapping_path = Path(mapping_path)
        self._by_normalized: dict[str, DevicePortInfo] = {}
        self._by_code: dict[str, DevicePortInfo] = {}
        self._by_display_name: dict[str, DevicePortInfo] = {}
        self._by_enum: dict[str, DevicePortInfo] = {}
        self._devices: list[DevicePortInfo] = []
        self._load()

    def _load(self) -> None:
        if not self.mapping_path.exists():
            logger.warning(f"[DEVICE_PORT_REGISTRY] Mapping file not found at {self.mapping_path}")
            return

        try:
            with open(self.mapping_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for item in data:
                info = DevicePortInfo(
                    enum_name=item["enum_name"],
                    code=item["code"],
                    display_name=item["display_name"],
                    expected_port=str(item["port"]).strip(),
                )
                self._devices.append(info)
                self._by_enum[item["enum_name"].lower()] = info
                self._by_code[item["code"].lower()] = info
                self._by_display_name[item["display_name"].lower()] = info
                self._by_normalized[_normalize_key(item["enum_name"])] = info
                self._by_normalized[_normalize_key(item["code"])] = info
                self._by_normalized[_normalize_key(item["display_name"])] = info
            logger.debug(f"[DEVICE_PORT_REGISTRY] Loaded {len(self._devices)} device port mappings")
        except Exception as exc:
            logger.error(f"[DEVICE_PORT_REGISTRY] Failed loading mapping file: {exc}")

    def get_device_port_info(self, device_type_or_code: str) -> Optional[DevicePortInfo]:
        """Look up device info by model name, display name, code, or enum name."""
        if not device_type_or_code or not str(device_type_or_code).strip():
            return None

        raw = str(device_type_or_code).strip()
        low = raw.lower()

        # 1. Direct lowercase checks
        if low in self._by_display_name:
            return self._by_display_name[low]
        if low in self._by_code:
            return self._by_code[low]
        if low in self._by_enum:
            return self._by_enum[low]

        # 2. Normalized alphanumeric check
        norm = _normalize_key(raw)
        if norm in self._by_normalized:
            return self._by_normalized[norm]

        # 3. Substring match for compound names (e.g., "Concox V5 4G" matching "Concox V5")
        for dev in self._devices:
            dev_norm = _normalize_key(dev.display_name)
            if dev_norm and (dev_norm in norm or norm in dev_norm):
                return dev

        return None

    def get_expected_port(self, device_type_or_code: str) -> Optional[str]:
        info = self.get_device_port_info(device_type_or_code)
        return info.expected_port if info else None

    def is_port_matching(self, device_type_or_code: str, actual_port: Any) -> Optional[bool]:
        """Return True if actual_port matches expected_port, False if mismatch or not configured, None if unknown device."""
        if not is_port_configured(actual_port):
            return False
        info = self.get_device_port_info(device_type_or_code)
        if not info:
            return None
        if not is_port_configured(info.expected_port):
            return False
        return str(actual_port).strip() == str(info.expected_port).strip()


def is_port_configured(port: Any) -> bool:
    """Return True if port is configured (not None, not empty, and not '0'). Port 0 means not configured."""
    if port is None:
        return False
    p_str = str(port).strip()
    return p_str != "" and p_str != "0"


# Singleton global instance
_GLOBAL_REGISTRY: Optional[DevicePortRegistry] = None


def get_global_device_port_registry() -> DevicePortRegistry:
    global _GLOBAL_REGISTRY
    if _GLOBAL_REGISTRY is None:
        _GLOBAL_REGISTRY = DevicePortRegistry()
    return _GLOBAL_REGISTRY


def get_device_port_info(device_type: str) -> Optional[DevicePortInfo]:
    return get_global_device_port_registry().get_device_port_info(device_type)


def get_expected_port(device_type: str) -> Optional[str]:
    return get_global_device_port_registry().get_expected_port(device_type)


def is_port_matching(device_type: str, actual_port: Any) -> Optional[bool]:
    return get_global_device_port_registry().is_port_matching(device_type, actual_port)


def build_port_fix_command(device_type: str, expected_port: str, command_registry: Any = None) -> Optional[str]:
    """Retrieve or construct the SMS server command with the expected port if available."""
    if not command_registry or not hasattr(command_registry, "get_configuration"):
        return None
    try:
        cfg = command_registry.get_configuration(device_type)
        if not cfg or not isinstance(cfg, dict):
            return None
        server_cmd = cfg.get("server")
        if not server_cmd:
            return None
        old_port = str(cfg.get("port") or "")
        if old_port and old_port in server_cmd:
            return server_cmd.replace(old_port, expected_port)
        # Regex substitution of 4-5 digit port number in server command template
        return re.sub(r"(?<=[,\s#:])\d{4,5}(?=[,\s#]|$)", expected_port, server_cmd)
    except Exception as exc:
        logger.debug(f"[DEVICE_PORT_REGISTRY] Could not build server command for {device_type}: {exc}")
        return None


def format_port_mismatch_message(
    vehicle_no: str,
    device_type: str,
    actual_port: Any,
    expected_port: str,
    command_registry: Any = None,
) -> str:
    """Generate user guidance instructing them to fix the port configuration."""
    base_msg = (
        f"Vehicle {vehicle_no} is currently unreachable. The device is configured on port {actual_port}, "
        f"but {device_type} requires port {expected_port} to communicate with TrackoBit."
    )
    cmd = build_port_fix_command(device_type, expected_port, command_registry)
    if cmd:
        instruction = (
            f"\n\nPlease fix the port configuration on your tracker. You can reconfigure it via SMS by "
            f"sending the following command to the device's SIM card:\n"
            f"```\n{cmd}\n```\n\n"
            f"Please reply once you have updated the port."
        )
    else:
        instruction = (
            f"\n\nPlease fix the port configuration by reconfiguring the tracker to point to port {expected_port} "
            f"(via SMS or device configuration tool).\n\n"
            f"Please reply once you have updated the port."
        )
    return base_msg + instruction
