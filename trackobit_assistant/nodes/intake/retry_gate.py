from trackobit_assistant.services.retry_policy import next_retry

def make_node(runtime):
    """Generic retry node. Inputs: retry_step/retry_message. Outputs: bounded per-step retry state."""
    def node(state):
        step=state.get('retry_step') or 'unknown'
        counters, retry_allowed, count=next_retry(state.get('retry_counters') or {},step,runtime.settings.max_input_retries)
        if not retry_allowed:
            return {'retry_counters':counters,'retry_exhausted':True,'handoff_reason':f'{step}_retry_exhausted',
                'response':f"I still couldn’t complete the {step.replace('_',' ')} step after {count} attempts. I’ll hand this over to support so you don’t have to keep retrying.",
                'awaiting':'none','current_step':'human_handoff'}
        message=state.get('retry_message') or f'Please try that again (attempt {count} of {runtime.settings.max_input_retries}).'
        if step=='vehicle_no':
            message+=f' (Attempt {count} of {runtime.settings.max_input_retries}.)'
            awaiting='vehicle_no'; paused='waiting for a valid vehicle number'; next_step='validate_vehicle_no'
        elif step=='workflow_choice':
            awaiting='workflow_choice'; paused='waiting for the user to choose a paused workflow'; next_step='resume_chosen_workflow'
        else:
            awaiting=state.get('awaiting','none'); paused=state.get('paused_at_step'); next_step=state.get('current_step')
        return {'retry_counters':counters,'retry_exhausted':False,'response':message,'awaiting':awaiting,
                'paused_at_step':paused,'current_step':next_step}
    return node
