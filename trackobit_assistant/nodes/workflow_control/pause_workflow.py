from trackobit_assistant.services.workflow_stack import pause_active

def make_node(runtime):
    def node(state):
        active_id=state.get('active_frame_id')
        stack,_=pause_active(state.get('workflow_stack') or [],active_id,state.get('paused_at_step')) if active_id else (list(state.get('workflow_stack') or []),None)
        return {'workflow_stack':stack,'active_frame_id':None,'active_workflow':'none','paused_active_workflow':bool(active_id)}
    return node
