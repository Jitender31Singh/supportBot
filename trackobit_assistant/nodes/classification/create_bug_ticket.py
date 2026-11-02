"""Software issue node.

Turn 1  — API data is healthy but user reports a display problem:
           Ask the user to refresh the page/app first.

Turn 2  — User confirms whether refresh fixed it:
           • Fixed  → close cleanly with a friendly message.
           • Still there → silently create an internal support ticket
             and reassure the user in plain language (no IDs, no tech jargon).
"""
import logging
from trackobit_assistant.services.summarizer import summarize_session

logger = logging.getLogger(__name__)

# Simple sentiment helpers (re-uses the same patterns as check_config)
import re
_YES = re.compile(
    r"\b(yes|y+e+s*|yeah|yep|yup|sure|ok(?:ay)?|fixed|working|updated|resolved|done|it(?:'?s| is) (?:working|updating|fine|showing)|now (?:it'?s?|showing|updating|working))\b",
    re.IGNORECASE
)
_NO = re.compile(
    r"\b(no+|nah|nope|still|same|not\s+(?:yet|working|showing|updating|fixed)|still\s+(?:not|same)|doesn'?t|don'?t|problem|issue|issue\s+persist)\b",
    re.IGNORECASE
)


def _is_resolved(text: str) -> bool:
    return bool(_YES.search(text)) and not bool(_NO.search(text))


def _is_still_issue(text: str) -> bool:
    return bool(_NO.search(text))


def make_node(runtime):
    def node(state):
        session_id = state.get('session_id', '-')
        awaiting   = state.get('awaiting', 'none')
        user_msg   = state.get('last_user_message', '').strip()
        vehicle_no = state.get('vehicle_no', 'your vehicle')

        # ── Turn 1: First time we land here — ask user to refresh ────────────
        if awaiting != 'software_refresh_confirm':

            # 1a. Check known active bug first (existing logic retained)
            bug_store = getattr(runtime, 'bug_store', None)
            if bug_store is not None:
                query = f"{user_msg} {(state.get('symptoms') or {}).get('summary', '')}".strip()
                try:
                    matched_bug = bug_store.search_active_bug(
                        query, llm=runtime.llm, module=state.get('selected_module')
                    )
                except Exception as e:
                    logger.warning(f"[SOFTWARE_CHECK] Bug store search error: {e}")
                    matched_bug = None

                if matched_bug:
                    workaround = matched_bug.get('workaround') or 'Our team is actively working on resolving this.'
                    logger.info(f"[SOFTWARE_CHECK] Matched known bug {matched_bug.get('bug_id')}")
                    return {
                        'response': (
                            f"We're aware of a temporary issue that may be affecting your view. "
                            f"Our team is already working on it.\n\n"
                            f"**What you can do now**: {workaround}\n\n"
                            f"If it doesn't resolve shortly, please reach out again and we'll assist you further."
                        ),
                        'fault_category': 'known_software_outage',
                        'resolved': True,
                        'known_bug': matched_bug,
                        'current_step': 'complete_frame',
                        'awaiting': 'none',
                    }

            # 1b. No known bug — ask user to do a simple refresh first
            logger.info(f"[SOFTWARE_CHECK] API data healthy; prompting user to refresh before creating ticket", extra={'session_id': session_id})
            return {
                'awaiting': 'software_refresh_confirm',
                'current_step': 'create_bug_ticket',
                'response': (
                    f"Good news — we checked your vehicle **{vehicle_no}** and it is actively "
                    f"connected and sending live data to our servers. "
                    f"This means the issue is likely a temporary display delay on your screen.\n\n"
                    f"**Please try the following:**\n"
                    f"• Refresh your browser page (or press **Ctrl + Shift + R** for a hard refresh)\n"
                    f"• If you're on the mobile app, close and reopen it\n"
                    f"• Log out and log back in if the above doesn't help\n\n"
                    f"Let me know — did the tracking update after refreshing?"
                ),
            }

        # ── Turn 2: User replied after refreshing ────────────────────────────
        logger.info(
            f"[SOFTWARE_CHECK] Received refresh confirmation from user: '{user_msg}'",
            extra={'session_id': session_id}
        )

        # Case A: Refresh fixed it
        if _is_resolved(user_msg):
            logger.info("[SOFTWARE_CHECK] User confirmed issue resolved after refresh", extra={'session_id': session_id})
            return {
                'resolved': True,
                'awaiting': 'none',
                'current_step': 'complete_frame',
                'response': (
                    f"That's great to hear! Glad the refresh did the trick. "
                    f"Your vehicle **{vehicle_no}** is now tracking normally. "
                    f"Feel free to reach out if you need anything else — happy to help!"
                ),
            }

        # Case B: Still not resolved — silently create internal ticket
        if _is_still_issue(user_msg) or user_msg:
            logger.info("[SOFTWARE_CHECK] Issue persists after refresh; creating internal ticket silently", extra={'session_id': session_id})
            summary = summarize_session(state)
            metadata = {
                'session_id':        state.get('session_id'),
                'vehicle_no':        vehicle_no,
                'device_type':       (state.get('vehicle_snapshot') or {}).get('device_type'),
                'snapshot':          state.get('vehicle_snapshot'),
                'dashboard_evidence':state.get('dashboard_evidence'),
                'fault_evidence':    state.get('fault_evidence'),
                'assigned_to':       runtime.settings.assign_to_support_user,
            }
            try:
                ticket = runtime.ticket_client.create(
                    summary=summary,
                    reason='software_issue',
                    metadata=metadata
                )
                # Save ticket internally — never expose ID or technical details to user
                logger.info(f"[SOFTWARE_CHECK] Ticket created: {ticket.ticket_id}", extra={'session_id': session_id})
                ticket_info = ticket.model_dump(mode='json')
            except Exception as exc:
                logger.warning(f"[SOFTWARE_CHECK] Ticket creation failed: {type(exc).__name__}: {exc}", extra={'session_id': session_id})
                ticket_info = None

            return {
                'ticket_info':    ticket_info,
                'awaiting':       'none',
                'resolved':       False,
                'current_step':   'complete_frame',
                # Clean, user-friendly message — no ticket ID, no API terms
                'response': (
                    f"Thank you for checking. We've noted that the display issue is persisting "
                    f"for vehicle **{vehicle_no}** even after a refresh.\n\n"
                    f"Our technical team has been informed and is looking into it on your account. "
                    f"You don't need to do anything further — we'll get this sorted for you. "
                    f"If the issue continues for an extended period, feel free to reach out and we'll follow up."
                ),
            }

        # Fallback — ambiguous reply, ask again
        return {
            'awaiting': 'software_refresh_confirm',
            'current_step': 'create_bug_ticket',
            'response': (
                "Just to confirm — after refreshing your page or app, is the vehicle location now "
                "updating on your screen? Please reply with **Yes** if it's working, or **No** if "
                "the issue is still there."
            ),
        }

    return node
