def make_node(runtime):
    def node(state):
        response = runtime.messages.render("ask_vehicle_no.md.j2", example="HR85G2799") if runtime.messages else ""
        if not response:
            response = "I can check the tracker status. What is the vehicle number as it appears in TrackoBit? For example: `HR85G2799`."
        return {"response": response, "awaiting": "vehicle_no",
                "paused_at_step": "waiting for the vehicle number", "active_workflow": "diagnosis", "current_step": "ask_vehicle_no"}
    return node
