import logging
from langchain_core.messages import SystemMessage
from trackobit_assistant.schemas.models import QueryClassification, QueryKind

logger = logging.getLogger('trackobit_assistant.nodes.query_classifier')

COMMAND_PHRASES = (
    'command for', 'commands for', 'command of', 'commands of',
    'what command', 'which command', 'what are the commands',
    'what is the command', 'what is the commands', 'commands to', 'command to',
    'list commands', 'show commands', 'commands list'
)

def make_node(runtime):
    def node(state):
        session_id = state.get('session_id', '-')
        raw_text = state.get('last_user_message') or ''
        text = raw_text.casefold()

        # Check for device command inquiries
        found_device = runtime.command_registry.find_device_in_text(raw_text) if getattr(runtime, 'command_registry', None) else None
        is_cmd_query = any(k in text for k in COMMAND_PHRASES) or (
            ('command' in text or 'commands' in text) and (bool(found_device) or any(w in text for w in ('device', 'tracker', 'device type', 'model')))
        )

        static = any(k in text for k in ('how do i', 'how to', 'add vehicle', 'geofence', 'feature', 'pricing', 'subscription plan', 'report', 'export', 'configure', 'what is', 'policy', 'settings'))
        result = None
        if runtime.llm is not None:
            try:
                prompt = (runtime.prompts.render('query_classifier', user_message=raw_text) if runtime.prompts else f'Classify as static_info, diagnosis, or device_commands: {text}')
                result = runtime.llm.with_structured_output(QueryClassification).invoke([SystemMessage(content=prompt)])
                logger.info(f"[QUERY_CLASSIFIER] LLM classified query: kind='{result.kind.value}' (conf={result.confidence:.2f}, reason='{result.reason}')", extra={'session_id': session_id})
            except Exception as exc:
                logger.warning(f"[QUERY_CLASSIFIER] LLM classification failed ({type(exc).__name__}: {exc}); using keyword baseline", extra={'session_id': session_id})
                result = None
        if result is None:
            if is_cmd_query:
                result = QueryClassification(kind=QueryKind.DEVICE_COMMANDS, confidence=0.92, reason='command query baseline', device_type=found_device)
            else:
                result = QueryClassification(kind=QueryKind.STATIC_INFO if static else QueryKind.DIAGNOSIS, confidence=0.83, reason='keyword baseline')
            logger.info(f"[QUERY_CLASSIFIER] Baseline classified query: kind='{result.kind.value}' (conf={result.confidence:.2f})", extra={'session_id': session_id})

        device_type_query = result.device_type or found_device
        return {
            'query_kind': result.kind.value,
            'query_confidence': result.confidence,
            'query_confidence_threshold': runtime.settings.query_confidence_threshold,
            'device_type_query': device_type_query,
            'response': ''
        }
    return node
