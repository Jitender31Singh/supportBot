from trackobit_assistant.services.workflow_stack import push

def make_node(runtime):
    """Inputs: query classification/session context. Output: new active frame."""
    def node(state):
        stack, frame_id = push(
            state.get('workflow_stack') or [],
            state.get('active_frame_id'),
            'diagnosis',
            {
                'symptoms': {},
                'command_history': [],
                'retry_counters': {},
                'vehicle_no': None,
                'vehicle_snapshot': None,
                'config_port_status': None,
                'config_device_type_status': None,
            },
            state.get('paused_at_step')
        )
        for f in stack:
            if f.get('frame_id') == frame_id:
                f['current_node'] = 'symptom_analyzer'
        return {
            'workflow_stack': stack,
            'active_frame_id': frame_id,
            'active_workflow': 'diagnosis',
            'awaiting': 'none',
            'response': '',
            'vehicle_no': None,
            'vehicle_snapshot': None,
            'snapshot_history': [],
            'config_port_status': None,
            'config_device_type_status': None,
            'config_subscription_status': None,
            'config_device_status': None,
            'config_movement_status': None,
            'symptoms': {},
            'command_history': [],
            'retry_counters': {},
            'current_command': None,
            'fault_category': None,
            'fault_evidence': [],
            'troubleshoot_rounds': 0,
            'ticket_info': None,
            'dashboard_evidence': None,
            'screenshot_retry_count': 0,
            'resolved': False,
            'handoff_reason': None
        }
    return node
