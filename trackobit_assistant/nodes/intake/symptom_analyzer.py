import logging
import re
from langchain_core.messages import SystemMessage
from trackobit_assistant.schemas.models import SymptomsResult
from trackobit_assistant.services.vehicle_normaliser import extract_vehicle_no

logger = logging.getLogger('trackobit_assistant.nodes.symptom_analyzer')

def make_node(runtime):
    def node(state):
        session_id = state.get('session_id', '-')
        text = state.get('last_user_message', '')
        result = None
        if runtime.llm is not None:
            try:
                prompt = (runtime.prompts.render('symptom_analyzer', user_message=text, vehicle_no=state.get('vehicle_no')) if runtime.prompts else f'Extract symptoms and a vehicle registration number from: {text}')
                result = runtime.llm.with_structured_output(SymptomsResult).invoke([SystemMessage(content=prompt)])
                logger.info(f"[SYMPTOM_ANALYZER] LLM extracted symptoms: summary='{result.summary}', vehicle='{result.vehicle_no}', urgency='{result.urgency}'", extra={'session_id': session_id})
            except Exception as exc:
                logger.warning(f"[SYMPTOM_ANALYZER] LLM symptom extraction failed ({type(exc).__name__}: {exc})", extra={'session_id': session_id})
                result = None

        candidate = extract_vehicle_no(text)
        other_vehicle = any(w in text.casefold() for w in ('another vehicle', 'different vehicle', 'second vehicle', 'another vehicle number', 'other vehicle', 'new vehicle', 'switch vehicle'))
        if candidate:
            vehicle = candidate
        elif other_vehicle:
            vehicle = None
        elif result and result.vehicle_no:
            vehicle = extract_vehicle_no(result.vehicle_no) or result.vehicle_no
        else:
            prev_veh = (
                state.get('workflow_stack')[-1].get('context', {}).get('vehicle_no')
                if state.get('workflow_stack')
                else None
            )
            vehicle = state.get('vehicle_no') or prev_veh

        old = state.get('symptoms') or {}
        device_match = re.search(r'(?i)\b(concox\s*v?\d*|teltonika|queclink|meitrack)\b', text)
        summary = (result.summary.strip() if result and result.summary else old.get('summary') or text.strip())
        symptoms = {
            **old,
            'summary': summary,
            'raw_user_message': text,
            'urgency': (result.urgency if result else ('high' if any(w in text.casefold() for w in ('urgent', 'emergency', 'stuck', 'safety')) else 'normal'))
        }
        mention = (result.device_type_mention if result else None) or (device_match.group(0) if device_match else None)
        if mention: symptoms['device_type_mention'] = mention
        if result and result.user_observation: symptoms['user_observation'] = result.user_observation
        logger.info(f"[SYMPTOM_ANALYZER] Output: vehicle_no='{vehicle}', device_type='{mention}', urgency='{symptoms.get('urgency')}', summary='{summary[:60]}'", extra={'session_id': session_id})

        # Check for known bugs early if bug_store is configured and user did not specify a vehicle
        bug_store = getattr(runtime, 'bug_store', None)
        if bug_store is not None and not vehicle:
            try:
                matched_bug = bug_store.search_active_bug(text, llm=runtime.llm)
            except Exception as e:
                logger.warning(f"[SYMPTOM_ANALYZER] Bug search failed: {e}")
                matched_bug = None

            if matched_bug:
                title = matched_bug.get('title')
                bug_id = matched_bug.get('bug_id')
                workaround = matched_bug.get('workaround') or 'Our engineering team is actively resolving this.'
                eta = matched_bug.get('eta') or 'in progress'
                resp = (
                    f"⚠️ We are currently aware of an ongoing issue matching your report: **{title}** (Reference: `{bug_id}`).\n\n"
                    f"• **Status**: Active (Fix ETA: {eta})\n"
                    f"• **Workaround**: {workaround}\n\n"
                    f"Our engineering team is already working on resolving this. "
                    f"If this is concerning a specific vehicle, feel free to share the vehicle registration number to check its device status."
                )
                return {
                    'symptoms': symptoms,
                    'vehicle_no': None,
                    'known_bug': matched_bug,
                    'response': resp,
                    'awaiting': 'none',
                    'resolved': True,
                    'fault_category': 'known_software_outage',
                }

        return {'symptoms': symptoms, 'vehicle_no': vehicle, 'response': '', 'awaiting': 'none'}
    return node
