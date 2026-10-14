from trackobit_assistant.nodes.workflow_control.target_helpers import choose_target

def make_node(runtime):
    def node(state):
        target=choose_target(state)
        if target:
            counters=dict(state.get('retry_counters') or {})
            counters.pop('workflow_choice',None)
            return {'target_frame_id':target,'retry_counters':counters,'workflow_choice_valid':True,'awaiting':'none','response':'Resuming the selected support issue.'}
        counters=dict(state.get('retry_counters') or {})
        attempt=counters.get('workflow_choice',0)+1; counters['workflow_choice']=attempt
        if attempt >= runtime.settings.max_input_retries:
            return {'retry_counters':counters,'workflow_choice_valid':False,'retry_exhausted':True,'handoff_reason':'workflow_choice_retry_exhausted','current_step':'human_handoff','response':'I still can’t tell which issue you meant. I’ll ask the support team to take over rather than resume the wrong workflow.'}
        frames=[f for f in (state.get('workflow_stack') or []) if f.get('status') in {'paused','stale'}]
        choices='\n'.join(f"{i+1}. {f.get('type','support')} — {f.get('paused_at_step') or 'previous step'}" for i,f in enumerate(frames))
        return {'retry_counters':counters,'workflow_choice_valid':False,'awaiting':'workflow_choice','response':f"I couldn’t match that to a paused issue (attempt {attempt} of {runtime.settings.max_input_retries}). Reply with one of these numbers:\n{choices}"}
    return node
