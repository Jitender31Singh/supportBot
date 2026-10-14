def make_node(runtime):
    def node(state):
        frames = [f for f in (state.get('workflow_stack') or []) if f.get('status') in {'paused', 'stale'}]
        if not frames:
            return {'response': 'There isn’t a paused workflow to resume. Tell me what you need help with.', 'awaiting': 'none'}
        lines = [f"{i + 1}. {f.get('type', 'support')} — {f.get('paused_at_step') or 'paused at an earlier step'}" for i, f in enumerate(frames)]
        formatted = runtime.messages.render('choose_workflow.md.j2', frames='\n'.join(lines)) if runtime.messages else ''
        if not formatted:
            formatted = 'Which issue should we continue? Reply with its number:\n' + '\n'.join(lines)
        return {'response': formatted, 'awaiting': 'workflow_choice',
                'paused_at_step': 'waiting for the user to choose a paused workflow', 'current_step': 'choose_workflow'}
    return node
