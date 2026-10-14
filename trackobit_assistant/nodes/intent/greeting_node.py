def make_node(runtime):
    def node(state):
        context = {"vehicle_no": state.get("vehicle_no") or ""}
        response = runtime.messages.render("greeting.md.j2", **context) if runtime.messages else ""
        if not response:
            response = "Hi! I’m the TrackoBit support assistant. Tell me what’s happening with your vehicle tracking, or ask a how-to question. If it’s a tracking issue, include the vehicle number when you’re ready."
        return {"response": response, "awaiting": state.get('awaiting', 'none'),
                'paused_at_step': state.get('paused_at_step'), 'current_step': state.get('current_step')}
    return node
