def make_node(runtime):
    def node(state):
        paused = [f for f in (state.get('workflow_stack') or []) if f.get('status') in {'paused', 'stale'}]
        response = state.get('response') or ''
        if paused and response and not state.get('resume_announcement'):
            items = '; '.join(f"{f.get('type', 'support')} — {f.get('paused_at_step') or 'previous step'}" for f in paused[-3:])
            footer = runtime.messages.render('paused_reminder.md.j2', paused_at_step=items) if runtime.messages else ''
            if not footer:
                footer = f"Still paused: {items}. Say “continue” when you’re ready to return."
            if 'Still paused:' not in response:
                response += '\n\n' + footer
        return {'response': response}
    return node
