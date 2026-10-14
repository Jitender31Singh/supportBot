import logging
from trackobit_assistant.services.command_selector import select_next_command

logger = logging.getLogger('trackobit_assistant.nodes.select_command')

def make_node(runtime):
    def node(state):
        session_id = state.get('session_id', '-')
        snapshot=state.get('vehicle_snapshot') or {}
        device=snapshot.get('device_type') or (state.get('symptoms') or {}).get('device_type_mention') or ''
        logger.info(f"[SELECT_COMMAND] Selecting command for device_type='{device}'", extra={'session_id': session_id})
        commands=runtime.command_registry.get_commands(device)
        if not commands:
            logger.warning(f"[SELECT_COMMAND] No commands found for device_type='{device}'; triggering handoff", extra={'session_id': session_id})
            return {'command_available':False,'handoff_reason':'unsupported_device_type','response':f"I don’t have a verified command sequence configured for device type `{device or 'unknown'}`. I’ll pass the diagnostic details to the support team rather than suggest a potentially incorrect command."}
        selected=select_next_command(commands,state.get('command_history') or [])
        if not selected:
            logger.warning(f"[SELECT_COMMAND] All commands exhausted for device_type='{device}'; triggering handoff", extra={'session_id': session_id})
            return {'command_available':False,'handoff_reason':'commands_exhausted','response':'I’ve completed the available automated device checks without a reliable conclusion. I’ll send the collected output and vehicle status to the support team.'}
        cmd=selected.model_dump(mode='json')
        logger.info(f"[SELECT_COMMAND] Selected command: id='{cmd.get('id')}', syntax='{cmd.get('command')}'", extra={'session_id': session_id})
        return {'command_available':True,'current_command':cmd,'active_workflow':'hardware_diagnosis','current_step':'present_command','response':''}
    return node

