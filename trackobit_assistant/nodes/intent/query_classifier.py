import logging
import re
from langchain_core.messages import SystemMessage
from trackobit_assistant.schemas.models import QueryClassification, QueryKind
from trackobit_assistant.nodes.session.recap_node import is_recap_query
from trackobit_assistant.services.vehicle_normaliser import VEHICLE_NO_SEARCH_PATTERN

logger = logging.getLogger('trackobit_assistant.nodes.query_classifier')

COMMAND_PHRASES = (
    'command for', 'commands for', 'command of', 'commands of',
    'what command', 'which command', 'what are the commands',
    'what is the command', 'what is the commands', 'commands to', 'command to',
    'list commands', 'show commands', 'commands list', 'device command', 'device commands'
)

def make_node(runtime):
    def node(state):
        session_id = state.get('session_id', '-')
        raw_text = state.get('last_user_message') or ''
        text = raw_text.casefold()

        if is_recap_query(raw_text):
            return {
                'query_kind': QueryKind.RECAP_CONVERSATION.value,
                'query_confidence': 0.98,
                'query_confidence_threshold': runtime.settings.query_confidence_threshold,
                'device_type_query': None,
                'response': ''
            }

        # Check if the query specifically concerns a vehicle (registration number or vehicle status/config inquiry)
        has_vehicle_no = bool(VEHICLE_NO_SEARCH_PATTERN.search(raw_text))
        is_vehicle_query = has_vehicle_no or any(phrase in text for phrase in (
            'vehicle number', 'my vehicle', 'this vehicle', 'for vehicle', 'with vehicle',
            'connected with vehicle', 'connected to vehicle', 'details of vehicle', 'details of the vehicle',
            'check vehicle configuration', 'configuration for vehicle', 'vehicle details', 'get vehicle',
            'another vehicle', 'different vehicle', 'second vehicle', 'another vehicle number', 'other vehicle', 'new vehicle'
        ))

        # Check for device command inquiries (e.g. asking for SMS/GPRS command reference)
        found_device = runtime.command_registry.find_device_in_text(raw_text) if getattr(runtime, 'command_registry', None) else None
        is_explicit_cmd = any(k in text for k in COMMAND_PHRASES)
        is_cmd_query = is_explicit_cmd or (
            ('command' in text or 'commands' in text) and (bool(found_device) or any(w in text for w in ('device', 'tracker', 'device type', 'model', 'sms command')))
        )

        static = any(k in text for k in (
            'how do i', 'how to', 'add vehicle', 'geofence', 'feature', 'pricing', 'subscription plan',
            'report', 'export', 'what is', 'policy', 'settings'
        ))

        result = None
        if runtime.llm is not None:
            try:
                prompt = (runtime.prompts.render('query_classifier', user_message=raw_text) if runtime.prompts else f'Classify as static_info, diagnosis, or device_commands: {text}')
                result = runtime.llm.with_structured_output(QueryClassification).invoke([SystemMessage(content=prompt)])
                logger.info(f"[QUERY_CLASSIFIER] LLM classified query: kind='{result.kind.value}' (conf={result.confidence:.2f}, reason='{result.reason}')", extra={'session_id': session_id})
            except Exception as exc:
                logger.warning(f"[QUERY_CLASSIFIER] LLM classification failed ({type(exc).__name__}: {exc}); using keyword baseline", extra={'session_id': session_id})
                result = None

        # Guardrail: Vehicle-specific status/config/telemetry inquiries must be diagnosis unless explicitly asking for command syntax
        if is_vehicle_query and not is_explicit_cmd:
            if result and result.kind in (QueryKind.DEVICE_COMMANDS, QueryKind.STATIC_INFO):
                logger.info(
                    f"[QUERY_CLASSIFIER] Overriding '{result.kind.value}' to 'diagnosis' for vehicle-specific inquiry: '{raw_text}'",
                    extra={'session_id': session_id}
                )
                result = QueryClassification(
                    kind=QueryKind.DIAGNOSIS,
                    confidence=0.96,
                    reason='Vehicle-specific configuration/status query belongs to diagnosis'
                )

        if result is None:
            if is_cmd_query and not is_vehicle_query:
                result = QueryClassification(kind=QueryKind.DEVICE_COMMANDS, confidence=0.92, reason='command query baseline', device_type=found_device)
            elif is_vehicle_query:
                result = QueryClassification(kind=QueryKind.DIAGNOSIS, confidence=0.95, reason='vehicle query baseline')
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
