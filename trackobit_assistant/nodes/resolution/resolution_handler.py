import logging
from typing import Any
from langchain_core.messages import SystemMessage
from trackobit_assistant.schemas.models import ResolutionVerdict, ResolutionResult

logger = logging.getLogger('trackobit_assistant.nodes.resolution_handler')

def _baseline_resolution(text: str) -> ResolutionResult:
    low = text.casefold().strip()
    if any(w in low for w in ('yes', 'resolved', 'fixed', 'working now', 'all good', 'it works', 'working fine', 'updated now', 'theek ho gaya', 'solved')):
        return ResolutionResult(verdict=ResolutionVerdict.RESOLVED, confidence=0.9, explanation='Affirmative keywords in baseline')
    if any(w in low for w in ('no', 'not yet', 'still not', 'did not', 'doesn’t work', 'doesnt work', 'still offline', 'not working', 'nahi hua', 'negative')):
        return ResolutionResult(verdict=ResolutionVerdict.NOT_RESOLVED, confidence=0.9, explanation='Negative keywords in baseline')
    return ResolutionResult(verdict=ResolutionVerdict.UNCLEAR, confidence=0.5, explanation='Ambiguous baseline')

def make_node(runtime):
    def node(state: dict[str, Any]) -> dict[str, Any]:
        session_id = state.get('session_id', '-')
        raw_text = state.get('last_user_message') or ''
        text = raw_text.strip()
        counters = dict(state.get('retry_counters') or {})

        result: ResolutionResult | None = None
        if runtime.llm is not None:
            try:
                # Gather recent conversation context for LLM reasoning
                history = []
                for msg in (state.get('messages') or [])[-6:]:
                    content = getattr(msg, 'content', str(msg))
                    if not isinstance(content, str):
                        content = str(content)
                    history.append(f"{getattr(msg, 'type', 'message')}: {content[:300]}")
                recent_context = "\n".join(history)

                prompt = (
                    runtime.prompts.render('resolution_handler', user_message=text, recent_context=recent_context)
                    if runtime.prompts else
                    f"Evaluate if the user's message indicates their vehicle tracking issue is resolved ('resolved'), not resolved ('not_resolved'), or unclear ('unclear').\nMessage: {text}\nContext:\n{recent_context}"
                )
                logger.debug(f"[RESOLUTION_HANDLER] Invoking LLM structured output for resolution evaluation...", extra={'session_id': session_id})
                result = runtime.llm.with_structured_output(ResolutionResult).invoke([SystemMessage(content=prompt)])
                logger.info(
                    f"[RESOLUTION_HANDLER] LLM evaluated resolution: verdict='{result.verdict.value}' (confidence={result.confidence:.2f}, explanation='{result.explanation}')",
                    extra={'session_id': session_id}
                )
            except Exception as exc:
                logger.warning(
                    f"[RESOLUTION_HANDLER] LLM evaluation failed ({type(exc).__name__}: {exc}); falling back to baseline",
                    extra={'session_id': session_id}
                )
                result = None

        if result is None:
            result = _baseline_resolution(text)
            logger.info(
                f"[RESOLUTION_HANDLER] Baseline evaluated resolution: verdict='{result.verdict.value}' (confidence={result.confidence:.2f})",
                extra={'session_id': session_id}
            )

        thresh = getattr(runtime.settings, 'query_confidence_threshold', 0.60)
        if result.confidence < thresh:
            logger.warning(
                f"[RESOLUTION_HANDLER] Resolution confidence {result.confidence:.2f} < threshold {thresh:.2f}; forcing verdict to UNCLEAR",
                extra={'session_id': session_id}
            )
            result.verdict = ResolutionVerdict.UNCLEAR

        if result.verdict == ResolutionVerdict.RESOLVED:
            counters.pop('resolution_confirm', None)
            logger.info("[RESOLUTION_HANDLER] User confirmed issue is resolved", extra={'session_id': session_id})
            return {
                'resolved': True,
                'retry_counters': counters,
                'response': 'Great — I’ve marked this support session as resolved. You can start a new chat any time if another vehicle has an issue.',
                'awaiting': 'none',
                'current_step': 'close_session'
            }

        if result.verdict == ResolutionVerdict.NOT_RESOLVED:
            counters.pop('resolution_confirm', None)
            logger.info("[RESOLUTION_HANDLER] User indicated issue is NOT resolved; continuing diagnosis", extra={'session_id': session_id})
            return {
                'resolved': False,
                'retry_counters': counters,
                'response': 'Thanks for confirming. I’ll continue with the next diagnostic step.',
                'awaiting': 'none',
                'current_step': 'continue_diagnosis'
            }

        # Ambiguous / Unclear response: retry policy or escalate to human
        attempts = counters.get('resolution_confirm', 0) + 1
        counters['resolution_confirm'] = attempts
        if attempts >= runtime.settings.max_input_retries:
            logger.warning(
                f"[RESOLUTION_HANDLER] Resolution confirmation retries exhausted ({attempts}); initiating handoff",
                extra={'session_id': session_id}
            )
            return {
                'retry_counters': counters,
                'retry_exhausted': True,
                'handoff_reason': 'resolution_confirmation_retry_exhausted',
                'current_step': 'human_handoff',
                'awaiting': 'none',
                'response': 'I still can’t tell whether the issue is fixed. I’ll ask a support specialist to follow up and confirm the outcome.'
            }

        logger.info(
            f"[RESOLUTION_HANDLER] Ambiguous reply for resolution confirmation: '{text}'. Attempt {attempts}/{runtime.settings.max_input_retries}",
            extra={'session_id': session_id}
        )
        return {
            'retry_counters': counters,
            'response': f'Please reply “yes” if it is fixed or “no” if the problem remains. (Attempt {attempts} of {runtime.settings.max_input_retries}.)',
            'awaiting': 'resolution_confirm',
            'paused_at_step': 'waiting for a yes/no resolution confirmation',
            'current_step': 'resolution_handler'
        }
    return node
