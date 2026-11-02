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
    'list commands', 'show commands', 'commands list', 'device command', 'device commands',
    'sms command', 'sms commands', 'gprs command', 'gprs commands'
)

STATIC_PATTERNS = (
    'how do i', 'how to', 'how can i', 'can i', 'where do i', 'where is', 'steps to',
    'add vehicle', 'create vehicle', 'geofence', 'feature', 'features', 'pricing',
    'subscription plan', 'subscription', 'report', 'reports', 'export', 'what is', 'policy', 'settings',
    'documentation', 'guide', 'manual'
)

SPECIFIC_VEHICLE_TARGET_PHRASES = (
    'my vehicle', 'this vehicle', 'the vehicle', 'connected with vehicle', 'connected to vehicle',
    'details of vehicle', 'details of the vehicle', 'check vehicle configuration',
    'configuration for vehicle', 'vehicle details', 'get vehicle details'
)

ISSUE_INDICATORS = (
    'not updating', 'not working', 'offline', 'stopped', 'wrong location',
    'no location', 'no data', 'delay', 'issue', 'problem', 'fault', 'error',
    'disconnected', 'tampered', 'battery low'
)

IMEI_PATTERN = re.compile(r'\b\d{15}\b')


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

        # 1. Identify specific entities (Vehicle registration number, IMEI, or targeted phrases)
        has_vehicle_no = bool(VEHICLE_NO_SEARCH_PATTERN.search(raw_text))
        has_imei = bool(IMEI_PATTERN.search(raw_text))

        # Check for device command inquiries (e.g. asking for SMS/GPRS command reference)
        found_device = runtime.command_registry.find_device_in_text(raw_text) if getattr(runtime, 'command_registry', None) else None
        is_explicit_cmd = any(k in text for k in COMMAND_PHRASES)
        is_cmd_query = is_explicit_cmd or (
            ('command' in text or 'commands' in text) and (bool(found_device) or any(w in text for w in ('device', 'tracker', 'device type', 'model', 'sms')))
        )

        is_static_inquiry = any(k in text for k in STATIC_PATTERNS)
        has_issue_reported = any(w in text for w in ISSUE_INDICATORS)

        # Distinguish specific vehicle targeting vs general static how-to inquiries
        has_specific_target = has_vehicle_no or has_imei or (
            any(p in text for p in SPECIFIC_VEHICLE_TARGET_PHRASES) and not (is_static_inquiry and not has_vehicle_no)
        )
        is_diagnostic_inquiry = (has_specific_target or has_issue_reported) and not (
            is_static_inquiry and not has_vehicle_no and not has_issue_reported
        )

        result = None
        if runtime.llm is not None:
            try:
                prompt = (runtime.prompts.render('query_classifier', user_message=raw_text) if runtime.prompts else f'Classify as static_info, diagnosis, or device_commands: {text}')
                result = runtime.llm.with_structured_output(QueryClassification).invoke([SystemMessage(content=prompt)])
                logger.info(f"[QUERY_CLASSIFIER] LLM classified query: kind='{result.kind.value}' (conf={result.confidence:.2f}, reason='{result.reason}')", extra={'session_id': session_id})
            except Exception as exc:
                logger.warning(f"[QUERY_CLASSIFIER] LLM classification failed ({type(exc).__name__}: {exc}); using keyword baseline", extra={'session_id': session_id})
                result = None

        # Guardrail: Specific vehicle/telemetry inquiries or reported issues must be diagnosis
        # unless explicitly asking for command syntax.
        # General product how-to queries without a vehicle number are NOT overridden.
        if is_diagnostic_inquiry and not is_explicit_cmd:
            if result and result.kind in (QueryKind.DEVICE_COMMANDS, QueryKind.STATIC_INFO):
                logger.info(
                    f"[QUERY_CLASSIFIER] Overriding '{result.kind.value}' to 'diagnosis' for vehicle/telemetry inquiry: '{raw_text}'",
                    extra={'session_id': session_id}
                )
                result = QueryClassification(
                    kind=QueryKind.DIAGNOSIS,
                    confidence=0.96,
                    reason='Vehicle-specific configuration/status query belongs to diagnosis'
                )

        if result is None:
            if is_cmd_query and not (has_vehicle_no and not is_explicit_cmd):
                result = QueryClassification(
                    kind=QueryKind.DEVICE_COMMANDS,
                    confidence=0.92,
                    reason='command query baseline',
                    device_type=found_device
                )
            elif is_diagnostic_inquiry:
                result = QueryClassification(
                    kind=QueryKind.DIAGNOSIS,
                    confidence=0.95,
                    reason='vehicle/telemetry query baseline'
                )
            else:
                result = QueryClassification(
                    kind=QueryKind.STATIC_INFO,
                    confidence=0.85,
                    reason='static info baseline'
                )
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
