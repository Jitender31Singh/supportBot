import logging
import re
from trackobit_assistant.services.vehicle_normaliser import extract_vehicle_no

logger = logging.getLogger('trackobit_assistant.nodes.validate_vehicle_no')

def make_node(runtime):
    def node(state):
        session_id = state.get('session_id', '-')
        raw = state.get('vehicle_no') or state.get('last_user_message', '')
        raw_str = str(raw).strip()

        # 1. Check if the user is describing an active known bug rather than answering with a vehicle plate
        bug_store = getattr(runtime, 'bug_store', None)
        if bug_store is not None:
            try:
                matched_bug = bug_store.search_active_bug(raw_str, llm=runtime.llm)
            except Exception as e:
                logger.warning(f"[VALIDATE_VEHICLE] Bug search failed: {e}")
                matched_bug = None

            if matched_bug:
                title = matched_bug.get('title')
                bug_id = matched_bug.get('bug_id')
                workaround = matched_bug.get('workaround') or 'Our engineering team is actively resolving this.'
                eta = matched_bug.get('eta') or 'in progress'
                logger.info(f"[VALIDATE_VEHICLE] User message matched active known bug {bug_id} ({title})")
                resp = (
                    f"⚠️ We have identified this as an active known issue: **{title}** (Reference: `{bug_id}`).\n\n"
                    f"• **Status**: Active (Fix ETA: {eta})\n"
                    f"• **Workaround**: {workaround}\n\n"
                    f"Our engineering team is already working on resolving this outage. "
                    f"If you need us to verify tracking for a specific vehicle, please share your vehicle registration number."
                )
                return {
                    'response': resp,
                    'awaiting': 'none',
                    'resolved': True,
                    'fault_category': 'known_software_outage',
                    'known_bug': matched_bug,
                    'vehicle_no_valid': False,
                    'current_step': 'complete_frame',
                }

        # 2. Extract and validate vehicle number
        extracted = extract_vehicle_no(raw_str)
        if not extracted:
            normalized = re.sub(r'[\s-]', '', raw_str.upper())
            if re.fullmatch(runtime.settings.vehicle_no_regex, normalized):
                extracted = normalized

        if not extracted or not re.fullmatch(runtime.settings.vehicle_no_regex, extracted):
            logger.warning(
                f"[VALIDATE_VEHICLE] Invalid vehicle number: '{raw_str}' does not match regex '{runtime.settings.vehicle_no_regex}'",
                extra={'session_id': session_id}
            )
            # If the user typed a descriptive sentence rather than a registration plate attempt
            if len(raw_str.split()) > 2 and not re.search(r'\d', raw_str):
                msg = 'I could not find a vehicle registration number in your message. To check tracking status, please provide the vehicle number (e.g. `HR85G2799`).'
            else:
                msg = f'That vehicle number does not match the expected format. I received `{raw_str}`; try a value like `HR85G2799`. Please check the letters and digits.'

            return {
                'vehicle_no': None,
                'vehicle_no_valid': False,
                'retry_step': 'vehicle_no',
                'retry_message': msg,
                'response': '',
                'awaiting': 'none',
                'current_step': 'retry_gate'
            }

        logger.info(f"[VALIDATE_VEHICLE] Successfully validated vehicle number: '{extracted}'", extra={'session_id': session_id})
        return {
            'vehicle_no': extracted,
            'vehicle_no_valid': True,
            'retry_exhausted': False,
            'awaiting': 'none',
            'response': '',
            'current_step': 'fetch_vehicle_info'
        }
    return node
