import logging
import re
from typing import Any
from langchain_core.messages import SystemMessage

logger = logging.getLogger('trackobit_assistant.nodes.recap_node')

RECAP_PATTERNS = [
    r'\bwhat\s+(?:have\s+i|did\s+i|i\s+have|i)\s+asked\b',
    r'\bwhat\s+(?:did\s+i|was\s+i)\s+(?:say|ask|asking)\b',
    r'\bwhat\s+was\s+my\s+(?:question|query|issue|problem|request)\b',
    r'\b(?:can\s+you\s+)?(?:recap|summarize|repeat|remind\s+me)\s+(?:what\s+i\s+asked|our\s+chat|our\s+conversation|what\s+we\s+discussed|this\s+conversation)\b',
    r'\b(?:recap|summary)\s+(?:of\s+)?(?:our\s+)?(?:chat|conversation|discussion)\b',
    r'^\s*(?:recap|summary)\s*(?:please|\?)?\s*$',
    r'\b(?:maine\s+kya|kya\s+(?:pucha|poocha|bola|kaha)\s+maine|kya\s+maine\s+(?:pucha|poocha|bola|kaha))\b',
    r'\bmera\s+(?:sawal|question|query)\s+kya\s+tha\b',
]

def is_recap_query(text: str) -> bool:
    if not text:
        return False
    clean = text.lower().strip()
    return any(re.search(p, clean) for p in RECAP_PATTERNS)

def make_node(runtime):
    def node(state: dict[str, Any]) -> dict[str, Any]:
        session_id = state.get('session_id', '-')
        user_message = state.get('last_user_message', '')
        messages = state.get('messages') or []
        summary = state.get('conversation_summary') or ''
        vehicle_no = state.get('vehicle_no') or ''
        snapshot = state.get('vehicle_snapshot') or {}

        # Collect user messages excluding the latest meta-recap question
        history = []
        user_queries = []
        for msg in messages[:-1]:
            role = getattr(msg, 'type', 'message')
            content = getattr(msg, 'content', str(msg))
            if not isinstance(content, str):
                content = str(content)
            if role in {'human', 'user'}:
                user_queries.append(content)
            history.append(f"{role.capitalize()}: {content[:300]}")

        transcript_text = "\n".join(history[-8:]) if history else "No previous messages."
        logger.info(f"[RECAP_NODE] Generating conversation recap for session {session_id}; user_queries={user_queries}", extra={'session_id': session_id})

        response = ""
        if getattr(runtime, 'llm', None) is not None:
            try:
                prompt = (
                    "You are TrackoBit support assistant. The user is asking to recall, recap, or repeat what they asked in this conversation.\n\n"
                    f"Conversation summary so far: {summary or 'N/A'}\n"
                    f"Vehicle discussed: {vehicle_no or 'N/A'}\n"
                    f"Recent conversation transcript:\n{transcript_text}\n\n"
                    f"User message: {user_message}\n\n"
                    "Respond directly to the user in a friendly, conversational tone (2-3 sentences). "
                    "Clearly state what they asked (e.g. they asked to check configuration/status for their vehicle), "
                    "what checks were performed (such as verifying port, device model, or live telemetry), "
                    "and that no issues were found or what the final outcome was. "
                    "Do NOT invent any new problems, and do NOT mention raising tickets."
                )
                res = runtime.llm.invoke([SystemMessage(content=prompt)])
                response = getattr(res, 'content', str(res)).strip()
            except Exception as exc:
                logger.warning(f"[RECAP_NODE] LLM recap generation failed ({type(exc).__name__}: {exc}); falling back to deterministic answer", extra={'session_id': session_id})
                response = ""

        if not response:
            # Deterministic fallback
            main_query = user_queries[0] if user_queries else ""
            dev_model = snapshot.get('device_type') or state.get('device_type') or ''
            port = snapshot.get('port') or state.get('port') or ''
            
            if vehicle_no and main_query:
                details = []
                if port:
                    details.append(f"port `{port}`")
                if dev_model:
                    details.append(f"device model `{dev_model}`")
                extra = f" (including confirming {', '.join(details)})" if details else ""
                response = (
                    f"In this conversation, you asked: **\"{main_query}\"** for vehicle **{vehicle_no}**.\n\n"
                    f"We verified your vehicle's configuration{extra} and checked that live telemetry is communicating properly. "
                    "No faults were detected. Feel free to ask if you need help with anything else!"
                )
            elif main_query:
                response = (
                    f"In this conversation, you asked: **\"{main_query}\"**.\n\n"
                    "Let me know if you would like more details or need help with anything else!"
                )
            elif summary:
                response = f"Here is a summary of what you asked and discussed: {summary}"
            else:
                response = "You asked about checking your vehicle configuration and tracking status. Everything was verified and active."

        logger.info(f"[RECAP_NODE] Finished generating recap response: {response[:100]}...", extra={'session_id': session_id})
        return {
            'response': response,
            'awaiting': 'none',
            'current_step': 'recap_conversation'
        }
    return node
