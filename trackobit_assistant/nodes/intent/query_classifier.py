import logging
from langchain_core.messages import SystemMessage
from trackobit_assistant.schemas.models import QueryClassification, QueryKind

logger = logging.getLogger('trackobit_assistant.nodes.query_classifier')

def make_node(runtime):
    def node(state):
        session_id = state.get('session_id', '-')
        text=(state.get('last_user_message') or '').casefold()
        static=any(k in text for k in ('how do i','how to','add vehicle','geofence','feature','pricing','subscription plan','report','export','configure','what is','policy','settings'))
        result=None
        if runtime.llm is not None:
            try:
                prompt=(runtime.prompts.render('query_classifier', user_message=state.get('last_user_message','')) if runtime.prompts else f'Classify as static_info or diagnosis: {text}')
                result=runtime.llm.with_structured_output(QueryClassification).invoke([SystemMessage(content=prompt)])
                logger.info(f"[QUERY_CLASSIFIER] LLM classified query: kind='{result.kind.value}' (conf={result.confidence:.2f}, reason='{result.reason}')", extra={'session_id': session_id})
            except Exception as exc:
                logger.warning(f"[QUERY_CLASSIFIER] LLM classification failed ({type(exc).__name__}: {exc}); using keyword baseline", extra={'session_id': session_id})
                result=None
        if result is None:
            result=QueryClassification(kind=QueryKind.STATIC_INFO if static else QueryKind.DIAGNOSIS, confidence=.83, reason='keyword baseline')
            logger.info(f"[QUERY_CLASSIFIER] Baseline classified query: kind='{result.kind.value}' (conf={result.confidence:.2f})", extra={'session_id': session_id})
        return {'query_kind':result.kind.value,'query_confidence':result.confidence,'query_confidence_threshold':runtime.settings.query_confidence_threshold,'response':''}
    return node
