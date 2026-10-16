import re
from typing import Any
from langchain_core.messages import SystemMessage
from trackobit_assistant.graph.runtime import Runtime
from trackobit_assistant.schemas.models import Intent, IntentResult
from trackobit_assistant.services.workflow_stack import summarize_for_prompt

GREETINGS={'hi','hello','hey','good morning','good afternoon','good evening','thanks','thank you','thx','ok thanks','🙏','👍'}
STATIC_WORDS=('how do i','how to','add vehicle','create vehicle','geofence','report','feature','pricing','subscription plan','export','configure','settings','policy','what is','command','commands')
ISSUE_WORDS=('not updating','not working','issue','problem','wrong location','gps','offline','no location','stopped','fault','error','device','vehicle')

def _heuristic(state: dict[str, Any], settings) -> IntentResult:
    text=(state.get('last_user_message') or '').strip()
    low=text.casefold()
    awaiting=(state.get('awaiting') or 'none')
    stack=state.get('workflow_stack') or []
    paused=[f for f in stack if f.get('status') in {'paused','stale'}]
    if low in GREETINGS and not any(w in low for w in ISSUE_WORDS): return IntentResult(intent=Intent.GREETING,confidence=.99,reasoning='Greeting/thanks')
    if awaiting == 'workflow_choice' and (low.isdigit() or any(f.get('type','').casefold() in low for f in paused)):
        return IntentResult(intent=Intent.ANSWERS_PENDING,confidence=.94,is_follow_up=True)
    if any(x in low for x in ('also another vehicle','another vehicle','different vehicle','second vehicle','another issue','also my')) and state.get('active_frame_id'):
        return IntentResult(intent=Intent.NEW_WORKFLOW,confidence=.9)
    if paused and any(phrase in low for phrase in ('i ran it', 'ran it', 'sent it', 'i sent the command', 'i did that', 'here is the output', 'here’s the output', 'here is the screenshot')):
        if len(paused) > 1:
            return IntentResult(intent=Intent.AMBIGUOUS_TARGET, confidence=.93, is_follow_up=True)
        return IntentResult(intent=Intent.RESUME_REQUEST, confidence=.91, is_follow_up=True, target_frame_id=paused[-1].get('frame_id'))
    static_side_question=any(w in low for w in ('geofence','add vehicle','how do i','how to','pricing','subscription','report','feature','export','configure','settings','command','commands'))
    if awaiting not in {'none',None,''} and state.get('active_frame_id') and static_side_question and not (awaiting in {'command_screenshot','command_screenshot_text'} and state.get('screenshot_path')):
        return IntentResult(intent=Intent.SIDE_QUESTION,confidence=.88)
    if awaiting not in {'none',None,''} and state.get('active_frame_id') and low in {'continue','resume','ok','okay','i ran it','run it again','repeat that step'}:
        return IntentResult(intent=Intent.RESUME_REQUEST,confidence=.9,is_follow_up=True,target_frame_id=state.get('active_frame_id'))
    if awaiting == 'resolution_confirm' and low in {'yes','y','resolved','fixed','working now','no','n','not yet','still not working'}:
        return IntentResult(intent=Intent.RESOLUTION_REPLY,confidence=.98,is_follow_up=True)
    if awaiting == 'vehicle_no' and text:
        return IntentResult(intent=Intent.ANSWERS_PENDING,confidence=.96,is_follow_up=True)
    if awaiting == 'stale_resume_confirm' and low in {'yes','y','no','n','fixed','resolved','not anymore','problem gone'}:
        return IntentResult(intent=Intent.ANSWERS_PENDING,confidence=.98,is_follow_up=True,target_frame_id=state.get('pending_resume_frame_id'))
    if awaiting in {'command_screenshot','command_screenshot_text'} and (state.get('screenshot_path') or any(w in low for w in ('gsm','gprs','gps','battery','status#','param#','satellite'))):
        secondary=[]
        if state.get('screenshot_path') and any(w in low for w in ('geofence','how do i','how to','add vehicle','pricing','report','feature')):
            secondary=[{'intent':'side_question','text':text}]
        return IntentResult(intent=Intent.ANSWERS_PENDING,confidence=.9,is_follow_up=True,intents=secondary)
    if awaiting == 'troubleshoot_result' and any(w in low for w in ('done','moved','checked','tried','yes','now updating','still not')):
        return IntentResult(intent=Intent.ANSWERS_PENDING,confidence=.91,is_follow_up=True)
    if awaiting == 'dashboard_evidence' and len(text) > 1:
        return IntentResult(intent=Intent.ANSWERS_PENDING,confidence=.9,is_follow_up=True)
    if low in {'continue','resume','go back','back to the issue','back to my issue','continue the previous issue'} or 'back to my gps' in low or 'continue the gps' in low:
        if len(paused)>1: return IntentResult(intent=Intent.AMBIGUOUS_TARGET,confidence=.94,is_follow_up=True)
        if paused: return IntentResult(intent=Intent.RESUME_REQUEST,confidence=.95,is_follow_up=True,target_frame_id=paused[-1].get('frame_id'))
        if state.get('active_frame_id'): return IntentResult(intent=Intent.RESUME_REQUEST,confidence=.95,is_follow_up=True,target_frame_id=state.get('active_frame_id'))
    if any(x in low for x in ('what was the command','which command','command again','what did you ask me to send')) and (paused or state.get('current_command')):
        return IntentResult(intent=Intent.REFERENCES_PAUSED,confidence=.9,is_follow_up=True,target_frame_id=(paused[-1].get('frame_id') if paused else state.get('active_frame_id')))
    if state.get('awaiting') not in {'none',None,''} and state.get('active_frame_id') and text:
        if any(x in low for x in ('geofence','add vehicle','how do i','pricing','subscription','report','feature','command','commands')):
            return IntentResult(intent=Intent.SIDE_QUESTION,confidence=.84)
        return IntentResult(intent=Intent.ANSWERS_PENDING,confidence=.76,is_follow_up=True)
    if any(w in low for w in ISSUE_WORDS) or len(text) > 18:
        return IntentResult(intent=Intent.NEW_QUERY,confidence=.82)
    if any(w in low for w in STATIC_WORDS): return IntentResult(intent=Intent.NEW_QUERY,confidence=.73)
    if text: return IntentResult(intent=Intent.UNCLEAR,confidence=.48,reasoning='Need more detail to classify the request')
    return IntentResult(intent=Intent.UNCLEAR,confidence=.1)

import logging

logger = logging.getLogger('trackobit_assistant.nodes.intent_parser')

def make_node(runtime: Runtime):
    def node(state: dict[str, Any]) -> dict[str, Any]:
        session_id = state.get('session_id', '-')
        user_message = state.get('last_user_message', '')
        awaiting = state.get('awaiting', 'none')
        active_wf = state.get('active_workflow', 'none')
        logger.info(f"[INTENT_PARSER] Evaluating user message: '{user_message}' (awaiting='{awaiting}', workflow='{active_wf}')", extra={'session_id': session_id})
        result = None
        if runtime.llm is not None:
            try:
                stack_summary = summarize_for_prompt(state.get('workflow_stack') or [])
                history = []
                for msg in (state.get('messages') or [])[-10:]:
                    content = getattr(msg, 'content', str(msg))
                    if not isinstance(content, str): content = str(content)
                    history.append(f"{getattr(msg, 'type', 'message')}: {content[:500]}")
                recent_messages = '\n'.join(history)
                prompt = (runtime.prompts.render('intent_parser', user_message=user_message, recent_messages=recent_messages, conversation_summary=state.get('conversation_summary', ''),
                    awaiting=awaiting, active_workflow=active_wf, stack_summary=stack_summary)
                    if runtime.prompts else f'Classify the user message. Summary: {state.get("conversation_summary","")}. Recent history: {recent_messages}. Stack: {stack_summary}. Message: {user_message}')
                logger.debug(f"[INTENT_PARSER] Invoking LLM structured output for intent classification...", extra={'session_id': session_id})
                result = runtime.llm.with_structured_output(IntentResult).invoke([SystemMessage(content=prompt)])
                logger.info(f"[INTENT_PARSER] LLM classified intent: '{result.intent.value}' (confidence={result.confidence:.2f}, reasoning='{result.reasoning}')", extra={'session_id': session_id})
            except Exception as exc:
                logger.warning(f"[INTENT_PARSER] LLM classification failed ({type(exc).__name__}: {exc}); falling back to heuristic parser", extra={'session_id': session_id})
                result = None
        if result is None:
            result = _heuristic(state, runtime.settings)
            logger.info(f"[INTENT_PARSER] Heuristic classified intent: '{result.intent.value}' (confidence={result.confidence:.2f}, reasoning='{result.reasoning}')", extra={'session_id': session_id})
        if result.confidence < runtime.settings.intent_confidence_threshold:
            logger.warning(f"[INTENT_PARSER] Intent confidence {result.confidence:.2f} < threshold {runtime.settings.intent_confidence_threshold:.2f}; forcing intent to UNCLEAR", extra={'session_id': session_id})
            result = IntentResult(intent=Intent.UNCLEAR, confidence=result.confidence, is_follow_up=result.is_follow_up, reasoning='Confidence below configured threshold')
        counters = dict(state.get('retry_counters') or {})
        if result.intent != Intent.UNCLEAR: counters.pop('unclear_intent', None)
        pending_intents = [item.model_dump() if hasattr(item, 'model_dump') else item for item in result.intents]
        logger.info(f"[INTENT_PARSER] Final decision: intent='{result.intent.value}' (confidence={result.confidence:.2f}, target_frame_id={result.target_frame_id})", extra={'session_id': session_id})
        return {'intent': result.intent.value, 'intent_confidence': result.confidence, 'pending_intents': pending_intents,
                'target_frame_id': result.target_frame_id, 'retry_counters': counters, 'response': '', 'intent_retry_exhausted': False}
    return node
