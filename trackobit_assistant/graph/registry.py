from trackobit_assistant.graph.runtime import Runtime
from trackobit_assistant.nodes.session.load_session import make_node as load_session
from trackobit_assistant.nodes.session.save_session import make_node as save_session
from trackobit_assistant.nodes.intent.intent_parser import make_node as intent_parser
from trackobit_assistant.nodes.intent.greeting_node import make_node as greeting_node
from trackobit_assistant.nodes.intent.clarify_node import make_node as clarify_node
from trackobit_assistant.nodes.intent.query_classifier import make_node as query_classifier
from trackobit_assistant.nodes.knowledge.rag_answer import make_node as rag_answer
from trackobit_assistant.nodes.intake.symptom_analyzer import make_node as symptom_analyzer
from trackobit_assistant.nodes.intake.ask_vehicle_no import make_node as ask_vehicle_no
from trackobit_assistant.nodes.intake.validate_vehicle_no import make_node as validate_vehicle_no
from trackobit_assistant.nodes.intake.fetch_vehicle_info import make_node as fetch_vehicle_info
from trackobit_assistant.nodes.intake.retry_gate import make_node as retry_gate
from trackobit_assistant.nodes.classification.fault_classifier import make_node as fault_classifier
from trackobit_assistant.nodes.classification.account_advice import make_node as account_advice
from trackobit_assistant.nodes.classification.create_bug_ticket import make_node as create_bug_ticket
from trackobit_assistant.nodes.workflow_control.notify_user import make_node as notify_user
from trackobit_assistant.nodes.troubleshooting.basic_troubleshooting import make_node as basic_troubleshooting
from trackobit_assistant.nodes.troubleshooting.recheck_vehicle_info import make_node as recheck_vehicle_info
from trackobit_assistant.nodes.troubleshooting.ask_dashboard_evidence import make_node as ask_dashboard_evidence
from trackobit_assistant.nodes.diagnosis.select_command import make_node as select_command
from trackobit_assistant.nodes.diagnosis.present_command import make_node as present_command
from trackobit_assistant.nodes.diagnosis.process_screenshot import make_node as process_screenshot
from trackobit_assistant.nodes.diagnosis.analyze_output import make_node as analyze_output
from trackobit_assistant.nodes.diagnosis.diagnosis_result import make_node as diagnosis_result
from trackobit_assistant.nodes.resolution.resolution_check import make_node as resolution_check
from trackobit_assistant.nodes.resolution.resolution_handler import make_node as resolution_handler
from trackobit_assistant.nodes.resolution.close_session import make_node as close_session
from trackobit_assistant.nodes.handoff.human_handoff import make_node as human_handoff
from trackobit_assistant.nodes.workflow_control.push_frame import make_node as push_frame
from trackobit_assistant.nodes.workflow_control.pause_workflow import make_node as pause_workflow
from trackobit_assistant.nodes.workflow_control.resume_workflow import make_node as resume_workflow
from trackobit_assistant.nodes.workflow_control.stale_resume_handler import make_node as stale_resume_handler
from trackobit_assistant.nodes.workflow_control.choose_workflow import make_node as choose_workflow
from trackobit_assistant.nodes.workflow_control.resolve_workflow_choice import make_node as resolve_workflow_choice
from trackobit_assistant.nodes.workflow_control.answer_from_paused import make_node as answer_from_paused
from trackobit_assistant.nodes.workflow_control.reminder_footer import make_node as reminder_footer
from trackobit_assistant.nodes.workflow_control.complete_frame import make_node as complete_frame
from trackobit_assistant.nodes.workflow_control.resume_router import make_node as resume_router
from trackobit_assistant.nodes.troubleshooting.update_dashboard_evidence import make_node as update_dashboard_evidence
from trackobit_assistant.nodes.knowledge.show_device_commands import make_node as show_device_commands


import logging
from typing import Any

logger = logging.getLogger('trackobit_assistant.nodes')

def _logged_node(name: str, fn):
    def wrapper(state: dict[str, Any], *args, **kwargs):
        session_id = state.get('session_id', '-')
        workflow = state.get('active_workflow', 'none')
        awaiting = state.get('awaiting', 'none')
        last_msg = (state.get('last_user_message') or '')[:80].replace('\n', ' ')
        logger.info(
            f"--> [NODE: {name}] START (workflow='{workflow}', awaiting='{awaiting}', user_msg='{last_msg}')",
            extra={'session_id': session_id}
        )
        try:
            updates = fn(state, *args, **kwargs)
            if isinstance(updates, dict):
                resp = ((updates.get('response') or '')[:70]).replace('\n', ' ')
                new_awaiting = updates.get('awaiting', awaiting)
                new_wf = updates.get('active_workflow', workflow)
                updated_keys = list(updates.keys())
                logger.info(
                    f"<-- [NODE: {name}] FINISHED (awaiting='{new_awaiting}', workflow='{new_wf}', updated_keys={updated_keys}, response='{resp}')",
                    extra={'session_id': session_id}
                )
            else:
                logger.info(f"<-- [NODE: {name}] FINISHED (result={type(updates).__name__})", extra={'session_id': session_id})
            return updates
        except Exception as exc:
            logger.exception(f"!!! [NODE: {name}] ERROR: {type(exc).__name__}: {exc}", extra={'session_id': session_id})
            raise
    return wrapper

def create_node_registry(runtime: Runtime):
    """Build the node map in one place; nodes remain factory-injected and independently testable."""
    nodes = {
      'load_session':load_session(runtime),'intent_parser':intent_parser(runtime),'greeting_node':greeting_node(runtime),
      'clarify_node':clarify_node(runtime),'query_classifier':query_classifier(runtime),'rag_answer':rag_answer(runtime),
      'symptom_analyzer':symptom_analyzer(runtime),'ask_vehicle_no':ask_vehicle_no(runtime),'validate_vehicle_no':validate_vehicle_no(runtime),
      'fetch_vehicle_info':fetch_vehicle_info(runtime),'retry_gate':retry_gate(runtime),'fault_classifier':fault_classifier(runtime),
      'account_advice':account_advice(runtime),'create_bug_ticket':create_bug_ticket(runtime),'notify_user':notify_user(runtime),
      'basic_troubleshooting':basic_troubleshooting(runtime),'recheck_vehicle_info':recheck_vehicle_info(runtime),
      'ask_dashboard_evidence':ask_dashboard_evidence(runtime),'select_command':select_command(runtime),'present_command':present_command(runtime),
      'process_screenshot':process_screenshot(runtime),'analyze_output':analyze_output(runtime),'diagnosis_result':diagnosis_result(runtime),
      'resolution_check':resolution_check(runtime),'resolution_handler':resolution_handler(runtime),'close_session':close_session(runtime),
      'human_handoff':human_handoff(runtime),'push_frame':push_frame(runtime),'pause_workflow':pause_workflow(runtime),
      'resume_workflow':resume_workflow(runtime),'stale_resume_handler':stale_resume_handler(runtime),'choose_workflow':choose_workflow(runtime),
      'resume_chosen_workflow':resolve_workflow_choice(runtime),'answer_from_paused':answer_from_paused(runtime),
      'reminder_footer':reminder_footer(runtime),'complete_frame':complete_frame(runtime),
      'update_dashboard_evidence':update_dashboard_evidence(runtime),
      'show_device_commands':show_device_commands(runtime),
      'resume_router':resume_router(runtime),
      'save_session':save_session(runtime),
    }
    return {name: _logged_node(name, fn) for name, fn in nodes.items()}

