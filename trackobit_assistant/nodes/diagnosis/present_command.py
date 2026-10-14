def make_node(runtime):
    def node(state):
        cmd = state.get("current_command") or {}
        context = {"order": cmd.get("order", ""), "purpose": cmd.get("purpose", ""),
                   "command": cmd.get("command", ""),
                   "how_to_send": cmd.get("how_to_send", "Follow your approved device command procedure.")}
        response = runtime.messages.render("present_command.md.j2", **context) if runtime.messages else ""
        if not response:
            response = (f"**Device check {context['order']} — {context['purpose']}**\n\nSend this exact command: `{context['command']}`\n\n"
                        f"{context['how_to_send']}\n\nPlease attach a clear screenshot of the full device reply. Don’t change the command text.")
        return {"response": response, "awaiting": "command_screenshot",
                "paused_at_step": f"waiting for the screenshot of {context['command'] or 'device command'} reply",
                "current_step": "present_command", "active_workflow": "hardware_diagnosis"}
    return node
