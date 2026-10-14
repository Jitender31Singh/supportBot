import logging

logger = logging.getLogger('trackobit_assistant.routes')

def route_intent(state):
    intent = state.get('intent', 'unclear')
    session_id = state.get('session_id', '-')
    awaiting = state.get('awaiting', 'none')
    if intent in {'answers_pending', 'follow_up'} and awaiting in {'none', None, ''}:
        logger.warning(f"[ROUTER: route_intent] intent='{intent}' but awaiting is '{awaiting}'; re-routing to 'query_classifier'", extra={'session_id': session_id})
        return 'query_classifier'
    target = {
      'greeting': 'greeting_node', 'smalltalk': 'greeting_node', 'unclear': 'clarify_node',
      'side_question': 'pause_workflow', 'resume_request': 'resume_workflow', 'references_paused': 'answer_from_paused',
      'ambiguous_target': 'choose_workflow', 'resolution_reply': 'resolution_handler',
      'answers_pending': 'resume_router', 'follow_up': 'resume_router', 'new_query': 'query_classifier', 'new_workflow': 'pause_workflow',
    }.get(intent, 'query_classifier')
    logger.info(f"[ROUTER: route_intent] intent='{intent}' (conf={state.get('intent_confidence')}) -> routing to '{target}'", extra={'session_id': session_id})
    return target

def route_after_query(state):
    session_id = state.get('session_id', '-')
    conf = float(state.get('query_confidence') or 0)
    thresh = float(state.get('query_confidence_threshold') or 0.60)
    kind = state.get('query_kind')
    if conf < thresh:
        logger.info(f"[ROUTER: route_after_query] query_confidence {conf:.2f} < threshold {thresh:.2f} -> routing to 'clarify_node'", extra={'session_id': session_id})
        return 'clarify_node'
    target = 'rag_answer' if kind == 'static_info' else 'push_frame'
    logger.info(f"[ROUTER: route_after_query] query_kind='{kind}' (conf={conf:.2f}) -> routing to '{target}'", extra={'session_id': session_id})
    return target

def route_after_rag(state):
    session_id = state.get('session_id', '-')
    paused = any(f.get('status') in {'paused', 'stale'} for f in (state.get('workflow_stack') or []))
    rag_conf = float(state.get('rag_confidence') or 0)
    thresh = float(state.get('rag_confidence_threshold') or 0.60)
    low_confidence = rag_conf < thresh
    if low_confidence and state.get('intent') not in {'side_question', 'references_paused'}:
        logger.info(f"[ROUTER: route_after_rag] low rag_confidence ({rag_conf:.2f} < {thresh:.2f}) -> routing to 'human_handoff'", extra={'session_id': session_id})
        return 'human_handoff'
    target = 'reminder_footer' if paused else 'save_session'
    logger.info(f"[ROUTER: route_after_rag] rag_confidence={rag_conf:.2f}, paused={paused} -> routing to '{target}'", extra={'session_id': session_id})
    return target

def route_after_symptoms(state):
    session_id = state.get('session_id', '-')
    v = state.get('vehicle_no')
    target = 'validate_vehicle_no' if v else 'ask_vehicle_no'
    logger.info(f"[ROUTER: route_after_symptoms] vehicle_no='{v}' -> routing to '{target}'", extra={'session_id': session_id})
    return target

def route_after_validate(state):
    session_id = state.get('session_id', '-')
    valid = state.get('vehicle_no_valid')
    exhausted = state.get('retry_exhausted')
    target = 'fetch_vehicle_info' if valid else ('human_handoff' if exhausted else 'retry_gate')
    logger.info(f"[ROUTER: route_after_validate] vehicle_no_valid={valid}, retry_exhausted={exhausted} -> routing to '{target}'", extra={'session_id': session_id})
    return target

def route_after_fetch(state):
    session_id = state.get('session_id', '-')
    api_ok = state.get('api_ok')
    target = 'fault_classifier' if api_ok else 'human_handoff'
    logger.info(f"[ROUTER: route_after_fetch] api_ok={api_ok} (error='{state.get('api_error')}') -> routing to '{target}'", extra={'session_id': session_id})
    return target

def route_after_fault(state):
    session_id = state.get('session_id', '-')
    category = state.get('fault_category')
    rounds = int(state.get('troubleshoot_rounds') or 0)
    max_rounds = int(state.get('max_troubleshoot_rounds') or 2)
    if category == 'account_issue': target = 'account_advice'
    elif category == 'software_issue': target = 'create_bug_ticket'
    elif category in {'hardware_issue', 'parked_ignition_off'}:
        target = 'select_command' if rounds >= max_rounds else 'basic_troubleshooting'
    elif category in {'need_more_info', 'unknown'}: target = 'ask_dashboard_evidence'
    else: target = 'resolution_check'
    logger.info(f"[ROUTER: route_after_fault] category='{category}', troubleshoot_rounds={rounds}/{max_rounds} -> routing to '{target}'", extra={'session_id': session_id})
    return target

def route_after_select_command(state):
    session_id = state.get('session_id', '-')
    avail = state.get('command_available')
    target = 'present_command' if avail else 'human_handoff'
    logger.info(f"[ROUTER: route_after_select_command] command_available={avail} -> routing to '{target}'", extra={'session_id': session_id})
    return target

def route_after_screenshot(state):
    session_id = state.get('session_id', '-')
    if state.get('handoff_reason'): target = 'human_handoff'
    elif state.get('parsed_command_output'): target = 'analyze_output'
    else: target = 'save_session'
    logger.info(f"[ROUTER: route_after_screenshot] handoff='{state.get('handoff_reason')}', has_output={bool(state.get('parsed_command_output'))} -> routing to '{target}'", extra={'session_id': session_id})
    return target

def route_after_analyze(state):
    session_id = state.get('session_id', '-')
    verdict = state.get('command_verdict')
    if verdict == 'issue_found': target = 'diagnosis_result'
    elif verdict == 'ok': target = 'resolution_check'
    else: target = 'select_command'
    logger.info(f"[ROUTER: route_after_analyze] verdict='{verdict}' -> routing to '{target}'", extra={'session_id': session_id})
    return target

def route_resume(state):
    session_id = state.get('session_id', '-')
    awaiting = state.get('awaiting', 'none')
    target = {'vehicle_no': 'validate_vehicle_no', 'dashboard_evidence': 'update_dashboard_evidence',
        'troubleshoot_result': 'recheck_vehicle_info', 'command_screenshot': 'process_screenshot',
        'command_screenshot_text': 'process_screenshot', 'resolution_confirm': 'resolution_handler',
        'workflow_choice': 'resume_chosen_workflow'}.get(awaiting, 'clarify_node')
    logger.info(f"[ROUTER: route_resume] awaiting='{awaiting}' -> routing to '{target}'", extra={'session_id': session_id})
    return target

def route_after_resolution(state):
    session_id = state.get('session_id', '-')
    if state.get('current_step') == 'human_handoff' or state.get('retry_exhausted'): target = 'human_handoff'
    elif state.get('resolved'): target = 'close_session'
    elif state.get('current_step') == 'continue_diagnosis': target = 'select_command'
    elif state.get('awaiting') == 'resolution_confirm': target = 'save_session'
    elif state.get('response') and state.get('awaiting') == 'none': target = 'save_session'
    else: target = 'human_handoff'
    logger.info(f"[ROUTER: route_after_resolution] resolved={state.get('resolved')}, step='{state.get('current_step')}' -> routing to '{target}'", extra={'session_id': session_id})
    return target

def route_after_complete(state):
    session_id = state.get('session_id', '-')
    has_paused = any(f.get('status') in {'paused', 'stale'} for f in state.get('workflow_stack', []))
    target = 'reminder_footer' if has_paused else 'save_session'
    logger.info(f"[ROUTER: route_after_complete] has_paused={has_paused} -> routing to '{target}'", extra={'session_id': session_id})
    return target

def route_after_resume(state):
    session_id = state.get('session_id', '-')
    target = 'save_session' if state.get('awaiting') == 'stale_resume_confirm' else 'resume_router'
    logger.info(f"[ROUTER: route_after_resume] awaiting='{state.get('awaiting')}' -> routing to '{target}'", extra={'session_id': session_id})
    return target

def route_after_stale_resume(state):
    session_id = state.get('session_id', '-')
    target = 'save_session' if state.get('current_step') == 'stale_resume_handler' else 'resume_router'
    logger.info(f"[ROUTER: route_after_stale_resume] current_step='{state.get('current_step')}' -> routing to '{target}'", extra={'session_id': session_id})
    return target

def route_after_retry_gate(state):
    session_id = state.get('session_id', '-')
    target = 'human_handoff' if state.get('retry_exhausted') else 'save_session'
    logger.info(f"[ROUTER: route_after_retry_gate] retry_exhausted={state.get('retry_exhausted')} -> routing to '{target}'", extra={'session_id': session_id})
    return target

def route_after_clarify(state):
    session_id = state.get('session_id', '-')
    target = 'human_handoff' if state.get('intent_retry_exhausted') else 'save_session'
    logger.info(f"[ROUTER: route_after_clarify] intent_retry_exhausted={state.get('intent_retry_exhausted')} -> routing to '{target}'", extra={'session_id': session_id})
    return target

def route_after_software_ticket(state):
    session_id = state.get('session_id', '-')
    target = 'human_handoff' if state.get('handoff_reason') == 'software_ticket_create_failed' else 'notify_user'
    logger.info(f"[ROUTER: route_after_software_ticket] handoff_reason='{state.get('handoff_reason')}' -> routing to '{target}'", extra={'session_id': session_id})
    return target

