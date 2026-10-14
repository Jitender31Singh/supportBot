from trackobit_assistant.services.workflow_stack import complete

def make_node(runtime):
    def node(state):
        outcome=state.get('handoff_reason') and 'escalated' or ('resolved' if state.get('resolved') else 'done')
        stack=complete(state.get('workflow_stack') or [],state.get('active_frame_id'),outcome,state.get('summary',''))
        most_recent=next((f for f in reversed(stack) if f.get('status') in {'paused','stale'}),None)
        return {'workflow_stack':stack,'active_frame_id':None,'active_workflow':'handoff' if outcome=='escalated' else 'none',
                'awaiting':'none','paused_to_resume':most_recent.get('frame_id') if most_recent else None}
    return node
