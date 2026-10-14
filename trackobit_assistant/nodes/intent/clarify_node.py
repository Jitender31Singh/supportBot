import logging

logger = logging.getLogger('trackobit_assistant.nodes.clarify')

def make_node(runtime):
    def node(state):
        session_id = state.get('session_id', '-')
        counters=dict(state.get('retry_counters') or {})
        attempts=counters.get('unclear_intent',0)+1
        counters['unclear_intent']=attempts
        last_msg = state.get('last_user_message', '')
        intent = state.get('intent', 'unclear')
        logger.warning(
            f"[CLARIFY_NODE] Triggered 'I don't understand': intent='{intent}', attempt={attempts}/{runtime.settings.max_input_retries}, last_message='{last_msg}'",
            extra={'session_id': session_id}
        )
        if attempts >= runtime.settings.max_input_retries:
            logger.warning(f"[CLARIFY_NODE] Max attempts exhausted ({attempts}); initiating human handoff", extra={'session_id': session_id})
            return {'retry_counters':counters,'intent_retry_exhausted':True,'retry_exhausted':True,
                'handoff_reason':'unclear_intent_retry_exhausted','current_step':'human_handoff',
                'response':'I still can’t confidently identify what you need after a few attempts. I’ll hand this conversation to the support team so you can explain it directly.'}
        return {'retry_counters':counters,'intent_retry_exhausted':False,
            'response':f'I’m not confident I understood that. Could you rephrase the issue in one sentence? For a tracking problem, mention what you see in the dashboard and the vehicle number if you have it. (Attempt {attempts} of {runtime.settings.max_input_retries}.)'}
    return node

