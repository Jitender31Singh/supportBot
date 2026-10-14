import logging
from typing import Any
from trackobit_assistant.graph.runtime import Runtime
from trackobit_assistant.services.workflow_stack import expire_stale

logger = logging.getLogger('trackobit_assistant.nodes.load_session')

def make_node(runtime: Runtime):
    """Inputs: persisted session state. Outputs: refreshed workflow stack and step metadata."""
    def node(state: dict[str, Any]) -> dict[str, Any]:
        session_id = state.get('session_id', '-')
        stack=expire_stale(state.get('workflow_stack') or [], runtime.settings.paused_frame_ttl_minutes, runtime.settings.paused_frame_max_age_hours)
        active=next((f for f in reversed(stack) if f.get('status') == 'active'), None)
        out={'workflow_stack':stack}
        if active:
            out.update({'active_frame_id':active.get('frame_id'),'active_workflow':active.get('type'),'awaiting':active.get('awaiting','none')})
            logger.info(f"[LOAD_SESSION] Active workflow frame restored: type='{active.get('type')}', awaiting='{active.get('awaiting','none')}', node='{active.get('current_node')}'", extra={'session_id': session_id})
        else:
            logger.info(f"[LOAD_SESSION] No active workflow frame. Stack depth: {len(stack)}", extra={'session_id': session_id})
        return out
    return node
