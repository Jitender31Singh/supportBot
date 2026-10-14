import logging
import re
from langchain_core.messages import SystemMessage
from trackobit_assistant.schemas.models import SymptomsResult

logger = logging.getLogger('trackobit_assistant.nodes.symptom_analyzer')

def make_node(runtime):
    def node(state):
        session_id = state.get('session_id', '-')
        text=state.get('last_user_message','')
        result=None
        if runtime.llm is not None:
            try:
                prompt=(runtime.prompts.render('symptom_analyzer',user_message=text,vehicle_no=state.get('vehicle_no')) if runtime.prompts else f'Extract symptoms and a vehicle registration number from: {text}')
                result=runtime.llm.with_structured_output(SymptomsResult).invoke([SystemMessage(content=prompt)])
                logger.info(f"[SYMPTOM_ANALYZER] LLM extracted symptoms: summary='{result.summary}', vehicle='{result.vehicle_no}', urgency='{result.urgency}'", extra={'session_id': session_id})
            except Exception as exc:
                logger.warning(f"[SYMPTOM_ANALYZER] LLM symptom extraction failed ({type(exc).__name__}: {exc})", extra={'session_id': session_id})
                result=None
        candidates=re.findall(r'(?i)\b[A-Z]{2}\s*[- ]?\d{1,2}\s*[- ]?[A-Z]{0,3}\s*[- ]?\d{4}\b',text)
        candidate=(re.sub(r'[\s-]','',candidates[0]).upper() if candidates else None)
        other_vehicle=any(w in text.casefold() for w in ('another vehicle','different vehicle','second vehicle'))
        vehicle=candidate or (result.vehicle_no if result and result.vehicle_no else (None if other_vehicle else state.get('vehicle_no')))
        old=state.get('symptoms') or {}
        device_match=re.search(r'(?i)\b(concox\s*v?\d*|teltonika|queclink|meitrack)\b',text)
        summary=(result.summary.strip() if result and result.summary else old.get('summary') or text.strip())
        symptoms={**old,'summary':summary,'raw_user_message':text,
            'urgency':(result.urgency if result else ('high' if any(w in text.casefold() for w in ('urgent','emergency','stuck','safety')) else 'normal'))}
        mention=(result.device_type_mention if result else None) or (device_match.group(0) if device_match else None)
        if mention: symptoms['device_type_mention']=mention
        if result and result.user_observation: symptoms['user_observation']=result.user_observation
        logger.info(f"[SYMPTOM_ANALYZER] Output: vehicle_no='{vehicle}', device_type='{mention}', urgency='{symptoms.get('urgency')}', summary='{summary[:60]}'", extra={'session_id': session_id})
        return {'symptoms':symptoms,'vehicle_no':vehicle,'response':'','awaiting':'none'}
    return node
