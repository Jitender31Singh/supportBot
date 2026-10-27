"""Route a pending user reply to the node that was awaiting it.

Inputs: active workflow frame fields ``awaiting`` and ``resume_represent_step``.
Outputs: ``resume_target``. Next edge: the selected step in graph/builder.py.
"""


import logging

logger = logging.getLogger('trackobit_assistant.nodes.resume_router')

def _resume_target(state):
    session_id = state.get('session_id', '-')
    awaiting = state.get('awaiting', 'none')
    if state.get('resume_represent_step'):
        target = {
            'vehicle_no': 'ask_vehicle_no', 'dashboard_evidence': 'ask_dashboard_evidence',
            'troubleshoot_result': 'basic_troubleshooting', 'command_screenshot': 'present_command',
            'command_screenshot_text': 'present_command', 'resolution_confirm': 'resolution_check',
            'workflow_choice': 'choose_workflow',
            'config_port_confirm': 'check_config', 'config_device_type_confirm': 'check_config',
            'subscription_renewal_confirm': 'check_config', 'device_activation_confirm': 'check_config',
            'config_move_vehicle': 'check_config',
        }.get(awaiting, 'clarify_node')
    else:
        target = {
            'vehicle_no': 'validate_vehicle_no', 'dashboard_evidence': 'update_dashboard_evidence',
            'troubleshoot_result': 'recheck_vehicle_info', 'command_screenshot': 'process_screenshot',
            'command_screenshot_text': 'process_screenshot', 'resolution_confirm': 'resolution_handler',
            'workflow_choice': 'resume_chosen_workflow', 'stale_resume_confirm': 'stale_resume_handler',
            'config_port_confirm': 'check_config', 'config_device_type_confirm': 'check_config',
            'subscription_renewal_confirm': 'check_config', 'device_activation_confirm': 'check_config',
            'config_move_vehicle': 'check_config',
        }.get(awaiting, 'clarify_node')

    if target == 'clarify_node':
        logger.warning(
            f"[RESUME ROUTER] awaiting='{awaiting}' has no matched target step! Falling back to clarify_node! (represent={state.get('resume_represent_step')})",
            extra={'session_id': session_id}
        )
    else:
        logger.info(
            f"[RESUME ROUTER] awaiting='{awaiting}' -> resume_target='{target}' (represent={state.get('resume_represent_step')})",
            extra={'session_id': session_id}
        )
    return target


def make_node(runtime):
    def node(state):
        return {'resume_target': _resume_target(state)}
    return node
