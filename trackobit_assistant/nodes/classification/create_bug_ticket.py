import logging
from trackobit_assistant.services.summarizer import summarize_session

logger = logging.getLogger(__name__)


def make_node(runtime):
    def node(state):
        summary = summarize_session(state)
        user_msg = state.get('last_user_message') or ''
        symptoms = state.get('symptoms') or {}
        symptoms_text = symptoms.get('summary') or user_msg

        # 1. Check Pinecone Bug Store for a known active outage or bug
        bug_store = getattr(runtime, 'bug_store', None)
        if bug_store is not None:
            query = f"{user_msg} {symptoms_text}".strip()
            try:
                matched_bug = bug_store.search_active_bug(query, llm=runtime.llm)
            except Exception as e:
                logger.warning(f"[CREATE_BUG_TICKET] Pinecone search error: {e}")
                matched_bug = None

            if matched_bug:
                title = matched_bug.get('title')
                bug_id = matched_bug.get('bug_id')
                workaround = matched_bug.get('workaround') or 'Our engineering team is actively resolving this.'
                eta = matched_bug.get('eta') or 'in progress'

                logger.info(f"[CREATE_BUG_TICKET] Matched active known bug {bug_id} ({title})")
                response_text = (
                    f"⚠️ We have identified this as an active known issue: **{title}** (Reference: `{bug_id}`).\n\n"
                    f"• **Status**: Active (Fix ETA: {eta})\n"
                    f"• **Workaround**: {workaround}\n\n"
                    f"Your vehicle tracking configuration is intact and telemetry is receiving updates normally. "
                    f"Our engineering team is already working on the fix, so no physical device inspection is required."
                )
                return {
                    'response': response_text,
                    'fault_category': 'known_software_outage',
                    'resolved': True,
                    'current_step': 'complete_frame',
                    'known_bug': matched_bug,
                }

        # 2. Fallback: If no known bug matches, create an internal support ticket
        metadata = {
            'session_id': state.get('session_id'),
            'vehicle_no': state.get('vehicle_no'),
            'device_type': (state.get('vehicle_snapshot') or {}).get('device_type'),
            'snapshot': state.get('vehicle_snapshot'),
            'dashboard_evidence': state.get('dashboard_evidence'),
            'assigned_to': runtime.settings.assign_to_support_user,
        }
        try:
            ticket = runtime.ticket_client.create(summary=summary, reason='software_issue', metadata=metadata)
            info = ticket.model_dump(mode='json')
            return {
                'ticket_info': info,
                'response': (
                    f"The vehicle API has a fresh update, but the dashboard is reported as stale or buffering, "
                    f"so this looks like a software/data-display issue. I’ve created support ticket **{ticket.ticket_id}** "
                    f"and assigned it to the support team. You don’t need to repeat the details from this chat."
                ),
                'handoff_reason': 'software_issue',
                'current_step': 'complete_frame',
            }
        except Exception as exc:
            return {
                'errors': (state.get('errors') or []) + [f'ticket_create:{type(exc).__name__}'],
                'handoff_reason': 'software_ticket_create_failed',
                'response': (
                    'This appears to be a software issue, but I could not create the internal ticket automatically. '
                    'I’m flagging the case for support with the information collected so far.'
                ),
            }
    return node
