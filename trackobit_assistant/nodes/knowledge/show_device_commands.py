import logging
from typing import Any

logger = logging.getLogger('trackobit_assistant.nodes.show_device_commands')

def make_node(runtime):
    def node(state: dict[str, Any]) -> dict[str, Any]:
        session_id = state.get('session_id', '-')
        user_message = state.get('last_user_message', '')
        device = state.get('device_type_query') or ''

        if not device and getattr(runtime, 'command_registry', None):
            device = runtime.command_registry.find_device_in_text(user_message) or ''

        registry = getattr(runtime, 'command_registry', None)
        display_name = registry.get_display_name(device) if (registry and device) else device
        logger.info(f"[SHOW_DEVICE_COMMANDS] Looking up commands for device='{device}' (display='{display_name}')", extra={'session_id': session_id})

        commands = registry.get_commands(device) if (registry and device) else []

        if not device:
            supported_list = registry.list_supported_devices()[:8] if registry else []
            supported = ", ".join(f"`{d}`" for d in supported_list)
            response = (
                "Please specify the device type you would like commands for.\n\n"
                f"Supported devices include: {supported}, and more."
            )
            return {'response': response, 'awaiting': 'none', 'active_workflow': 'none', 'current_step': 'show_device_commands'}

        if not commands:
            supported_list = registry.list_supported_devices()[:8] if registry else []
            supported = ", ".join(f"`{d}`" for d in supported_list)
            response = (
                f"I couldn't find verified commands for device type `{device}`.\n\n"
                f"Supported device types include: {supported}."
            )
            return {'response': response, 'awaiting': 'none', 'active_workflow': 'none', 'current_step': 'show_device_commands'}

        lines = [f"Here are the diagnostic commands for **{display_name}**:\n"]
        for cmd in commands:
            lines.append(f"{cmd.order}. **Command**: `{cmd.command}`")
            lines.append(f"   - **Purpose**: {cmd.purpose}")
            if cmd.how_to_send:
                lines.append(f"   - **How to send**: {cmd.how_to_send}")
            lines.append("")

        response = "\n".join(lines).strip()
        logger.info(f"[SHOW_DEVICE_COMMANDS] Returned {len(commands)} commands for '{display_name}'", extra={'session_id': session_id})
        return {'response': response, 'awaiting': 'none', 'active_workflow': 'none', 'current_step': 'show_device_commands'}
    return node
