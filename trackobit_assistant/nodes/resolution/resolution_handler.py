import logging

logger = logging.getLogger('trackobit_assistant.nodes.resolution_handler')

def make_node(runtime):
    def node(state):
        session_id = state.get('session_id', '-')
        text=(state.get('last_user_message') or '').casefold().strip()
        counters=dict(state.get('retry_counters') or {})
        if any(w in text for w in ('yes','resolved','fixed','working now')):
            counters.pop('resolution_confirm',None)
            logger.info("[RESOLUTION_HANDLER] User confirmed issue is resolved", extra={'session_id': session_id})
            return {'resolved':True,'retry_counters':counters,'response':'Great — I’ve marked this support session as resolved. You can start a new chat any time if another vehicle has an issue.','awaiting':'none','current_step':'close_session'}
        if any(w in text for w in ('no','not yet','still not','did not','doesn’t work','doesnt work')):
            counters.pop('resolution_confirm',None)
            logger.info("[RESOLUTION_HANDLER] User indicated issue is NOT resolved; continuing diagnosis", extra={'session_id': session_id})
            return {'resolved':False,'retry_counters':counters,'response':'Thanks for confirming. I’ll continue with the next diagnostic step.','awaiting':'none','current_step':'continue_diagnosis'}
        attempts=counters.get('resolution_confirm',0)+1; counters['resolution_confirm']=attempts
        if attempts >= runtime.settings.max_input_retries:
            logger.warning(f"[RESOLUTION_HANDLER] Resolution confirmation retries exhausted ({attempts}); initiating handoff", extra={'session_id': session_id})
            return {'retry_counters':counters,'retry_exhausted':True,'handoff_reason':'resolution_confirmation_retry_exhausted','current_step':'human_handoff','awaiting':'none',
                    'response':'I still can’t tell whether the issue is fixed. I’ll ask a support specialist to follow up and confirm the outcome.'}
        logger.info(f"[RESOLUTION_HANDLER] Ambiguous reply for resolution confirmation: '{text}'. Attempt {attempts}/{runtime.settings.max_input_retries}", extra={'session_id': session_id})
        return {'retry_counters':counters,'response':f'Please reply “yes” if it is fixed or “no” if the problem remains. (Attempt {attempts} of {runtime.settings.max_input_retries}.)',
                'awaiting':'resolution_confirm','paused_at_step':'waiting for a yes/no resolution confirmation','current_step':'resolution_handler'}
    return node

