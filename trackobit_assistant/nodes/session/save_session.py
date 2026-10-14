import logging
from uuid import uuid4
from typing import Any
from langchain_core.messages import AIMessage
from trackobit_assistant.services.workflow_stack import pause_active
from trackobit_assistant.services.conversation_memory import update_conversation_summary

logger = logging.getLogger('trackobit_assistant.nodes.save_session')

def make_node(runtime):
    """Inputs: response and current graph state. Outputs: assistant message plus a checkpoint-ready frame snapshot."""
    def node(state: dict[str, Any]) -> dict[str, Any]:
        session_id = state.get('session_id', '-')
        response=state.get('response') or 'I could not prepare a response. Please try again or contact support.'
        prefix=state.get('resume_prefix')
        if prefix and not response.startswith(prefix): response=f"{prefix}\n\n{response}"
        stack=[dict(frame) for frame in (state.get('workflow_stack') or [])]
        active_id=state.get('active_frame_id')
        awaiting=state.get('awaiting','none')
        logger.info(f"[SAVE_SESSION] Persisting turn: awaiting='{awaiting}', active_frame_id='{active_id}', stack_depth={len(stack)}", extra={'session_id': session_id})

        # Secondary side questions in a mixed turn are answered after the primary pending step.
        secondaries=[item for item in (state.get('pending_intents') or []) if item.get('intent')=='side_question']
        if secondaries:
            secondary_text=str(secondaries[-1].get('text') or secondaries[-1].get('query') or state.get('last_user_message') or '')
            if active_id:
                stack,_=pause_active(stack,active_id,state.get('paused_at_step'))
                for frame in stack:
                    if frame.get('frame_id')==active_id:
                        frame['current_node']=state.get('current_step') or frame.get('current_node')
                        frame['awaiting']=awaiting
                        frame['paused_at_step']=state.get('paused_at_step') or _step_description(state.get('current_step'),awaiting,state.get('current_command'))
                        context=dict(frame.get('context') or {})
                        for key in ('command_history','retry_counters','current_command','fault_category','fault_evidence','symptoms','troubleshoot_rounds','vehicle_no','vehicle_snapshot','snapshot_history','dashboard_evidence','ticket_info'):
                            if key in state: context[key]=state[key]
                        frame['context']=context
                active_id=None
            docs=runtime.knowledge_base.search(secondary_text,k=3)
            if docs:
                side_answer=f"For your side question, the closest approved knowledge-base match is:\n\n{docs[0]['content']}\n\nSource: {docs[0].get('source','knowledge base')}"
            else:
                side_answer="For your side question, I couldn’t find an approved answer in the current knowledge base, so I won’t guess. A support specialist can confirm the correct product steps."
            response+=f"\n\n---\n**Side question:** {secondary_text}\n\n{side_answer}"
            awaiting='none';
            if any(f.get('status') in {'paused','stale'} for f in stack):
                paused_labels='; '.join(f"{f.get('type','support')} — {f.get('paused_at_step') or 'previous step'}" for f in stack if f.get('status') in {'paused','stale'})
                response+=f"\n\nStill paused: {paused_labels}. Say “continue” when you’re ready to return."
        elif any(f.get('status') in {'paused','stale'} for f in stack) and state.get('intent') in {'side_question','references_paused'} and response:
            paused_labels='; '.join(f"{f.get('type','support')} — {f.get('paused_at_step') or 'previous step'}" for f in stack if f.get('status') in {'paused','stale'})
            if 'Still paused:' not in response: response+=f"\n\nStill paused: {paused_labels}. Say “continue” when you’re ready to return."
        for frame in stack:
            if frame.get('frame_id') == active_id and frame.get('status') == 'active':
                frame['current_node']=state.get('current_step') or frame.get('current_node')
                frame['awaiting']=awaiting
                frame['paused_at_step']=state.get('paused_at_step') or _step_description(state.get('current_step'),awaiting,state.get('current_command'))
                frame['updated_at']=__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat()
                context=dict(frame.get('context') or {})
                for key in ('command_history','retry_counters','current_command','fault_category','fault_evidence','ticket_info','symptoms','troubleshoot_rounds','vehicle_no','vehicle_snapshot','snapshot_history','dashboard_evidence'):
                    if key in state: context[key]=state[key]
                frame['context']=context
        transcript = list(state.get('messages') or []) + [AIMessage(content=response, id=str(uuid4()))]
        rolling_summary, summary_count = update_conversation_summary(
            transcript, state.get('conversation_summary') or '', state.get('summary_message_count') or 0
        )
        return {'response':response,'workflow_stack':stack,'active_frame_id':active_id,
                'active_workflow':('none' if active_id is None and secondaries else state.get('active_workflow','none')),
                'awaiting':awaiting,'conversation_summary':rolling_summary,'summary_message_count':summary_count,
                'messages':[AIMessage(content=response, id=str(uuid4()))]}
    return node

def _step_description(node, awaiting, command):
    if awaiting=='vehicle_no': return 'waiting for the vehicle number'
    if awaiting=='dashboard_evidence': return 'waiting for dashboard location/time evidence'
    if awaiting=='troubleshoot_result': return 'waiting for the user to report the troubleshooting result'
    if awaiting=='command_screenshot': return f"waiting for the screenshot of {(command or {}).get('command','the device command')} reply"
    if awaiting=='resolution_confirm': return 'waiting for a yes/no resolution confirmation'
    return f"paused at {node or 'the current support step'}"
