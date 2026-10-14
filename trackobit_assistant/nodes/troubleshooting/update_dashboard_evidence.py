"""Save the user's dashboard observation and send it back through deterministic fault rules.

Inputs: ``last_user_message``. Outputs: ``dashboard_evidence`` and clear awaiting state.
Next edge: ``fault_classifier``.
"""

def make_node(runtime):
    def node(state):
        return {
            'dashboard_evidence': state.get('last_user_message', ''),
            'awaiting': 'none',
            'response': '',
            'current_step': 'fault_classifier',
        }
    return node
