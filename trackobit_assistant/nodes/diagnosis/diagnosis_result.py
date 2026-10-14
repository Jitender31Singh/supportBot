def make_node(runtime):
    def node(state):
        history=state.get('command_history') or []
        result=state.get('command_analysis') or (history[-1] if history else {})
        response=f"The device check suggests: **{result.get('finding','a device issue was detected')}**.\n\n{result.get('advice','Please contact support for the next step.')}\n\nDoes the tracking issue work now?"
        return {'response':response,'awaiting':'resolution_confirm','paused_at_step':'waiting for the user to confirm whether the recommended fix resolved the issue','current_step':'resolution_check'}
    return node
