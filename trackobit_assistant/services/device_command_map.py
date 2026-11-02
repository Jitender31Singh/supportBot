"""Device command map service.

Provides a device-type-aware lookup for specific diagnostic commands
(e.g., 'status', 'param') from the YAML command registry, so the
fault_diagnosis node never needs to hardcode command strings.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from trackobit_assistant.adapters.command_registry import YamlCommandRegistry
    from trackobit_assistant.schemas.models import CommandSpec

logger = logging.getLogger('trackobit_assistant.services.device_command_map')

# Command IDs that represent a "device info / status" check across all device types.
# Order matters: first match wins.
_STATUS_COMMAND_IDS = {'status', 'deviceinfo', 'device_info', 'device info', 'param', 'getstatus'}
_PARAM_COMMAND_IDS  = {'param', 'imeiinfo', 'imei_info', 'gprsset', 'serverinfo', 'server_info'}


def _normalize(s: str) -> str:
    return s.strip().casefold()


def get_command_for_purpose(
    device_type: str,
    command_registry: 'YamlCommandRegistry',
    purpose_ids: set[str],
) -> 'CommandSpec | None':
    """Return the first command whose id (normalized) is in *purpose_ids* for this device type."""
    commands = command_registry.get_commands(device_type)
    for cmd in sorted(commands, key=lambda c: c.order):
        if _normalize(cmd.id) in purpose_ids:
            return cmd
    # Fallback: match by command syntax substring
    for cmd in sorted(commands, key=lambda c: c.order):
        cmd_text = _normalize(cmd.command)
        if any(pid.replace('_', '') in cmd_text.replace('#', '').replace(' ', '') for pid in purpose_ids):
            return cmd
    return None


def get_status_command(
    device_type: str,
    command_registry: 'YamlCommandRegistry',
) -> 'CommandSpec | None':
    """Return the STATUS (device-info) command for the given device type, or None."""
    cmd = get_command_for_purpose(device_type, command_registry, _STATUS_COMMAND_IDS)
    if cmd:
        logger.debug(f"[DEVICE_COMMAND_MAP] status command for '{device_type}': '{cmd.command}' (id={cmd.id})")
    else:
        logger.warning(f"[DEVICE_COMMAND_MAP] No status command found for device_type='{device_type}'")
    return cmd


def get_param_command(
    device_type: str,
    command_registry: 'YamlCommandRegistry',
) -> 'CommandSpec | None':
    """Return the PARAM (IMEI/server-info) command for the given device type, or None."""
    cmd = get_command_for_purpose(device_type, command_registry, _PARAM_COMMAND_IDS)
    if cmd:
        logger.debug(f"[DEVICE_COMMAND_MAP] param command for '{device_type}': '{cmd.command}' (id={cmd.id})")
    else:
        logger.warning(f"[DEVICE_COMMAND_MAP] No param command found for device_type='{device_type}'")
    return cmd


def describe_status_command(cmd: 'CommandSpec | None', device_type: str) -> str:
    """Return a human-readable instruction string for sending the status command."""
    if cmd is None:
        return (
            f"Please send the device status diagnostic command for your **{device_type}** tracker "
            f"via SMS or the TrackoBit command terminal, and share a screenshot of the full reply."
        )
    return (
        f"Please send `{cmd.command}` to the device via SMS or the TrackoBit command terminal, "
        f"and share a clear screenshot of the full reply."
    )
