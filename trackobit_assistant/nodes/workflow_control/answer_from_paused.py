def make_node(runtime):
    def node(state):
        frames = state.get('workflow_stack') or []
        target_id = state.get('target_frame_id') or state.get('active_frame_id')
        frame = next((f for f in frames if f.get('frame_id') == target_id), None)
        if frame is None:
            frame = next((f for f in reversed(frames) if f.get('status') in {'paused', 'stale'}), None)
        context = (frame or {}).get('context') or {}
        command = context.get('current_command') or state.get('current_command') or {}
        if command:
            answer = f"The command we were at was `{command.get('command', '')}` — {command.get('purpose', '')}."
        elif frame:
            answer = f"That issue was paused at: {frame.get('paused_at_step') or frame.get('current_node') or 'an earlier support step'}."
        else:
            answer = "I don’t have a saved command for this session yet. Tell me the vehicle issue and I’ll guide you through the next check."
        return {'response': answer, 'referenced_paused_frame': (frame or {}).get('frame_id')}
    return node
