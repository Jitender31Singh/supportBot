import logging
import re

logger = logging.getLogger('trackobit_assistant.nodes.validate_vehicle_no')

def make_node(runtime):
    def node(state):
        session_id = state.get('session_id', '-')
        raw=state.get('vehicle_no') or state.get('last_user_message','')
        normalized=re.sub(r'[\s-]','',str(raw).upper())
        if not re.fullmatch(runtime.settings.vehicle_no_regex,normalized):
            logger.warning(f"[VALIDATE_VEHICLE] Invalid vehicle number: '{raw}' (normalized='{normalized}') does not match regex '{runtime.settings.vehicle_no_regex}'", extra={'session_id': session_id})
            return {'vehicle_no':None,'vehicle_no_valid':False,'retry_step':'vehicle_no',
                    'retry_message':f'That vehicle number does not match the expected format. I received `{str(raw).strip()}`; try a value like `HR85G2799`. Please check the letters and digits.',
                    'response':'','awaiting':'none','current_step':'retry_gate'}
        logger.info(f"[VALIDATE_VEHICLE] Successfully validated vehicle number: '{normalized}'", extra={'session_id': session_id})
        return {'vehicle_no':normalized,'vehicle_no_valid':True,'retry_exhausted':False,'awaiting':'none','response':'','current_step':'fetch_vehicle_info'}
    return node

