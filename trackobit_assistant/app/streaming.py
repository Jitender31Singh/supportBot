"""Helpers for Server-Sent Events used by the chat API."""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any


_PROGRESS_LABELS = {
    "load_session": "Loading this conversation's saved context…",
    "intent_parser": "Understanding your message and current troubleshooting step…",
    "greeting_node": "Preparing a reply…",
    "clarify_node": "Checking what detail is needed next…",
    "query_classifier": "Choosing the right support path…",
    "rag_answer": "Searching the available support knowledge base…",
    "push_frame": "Starting a separate support workflow…",
    "symptom_analyzer": "Extracting the issue and any vehicle details…",
    "ask_vehicle_no": "Waiting for the vehicle number…",
    "validate_vehicle_no": "Validating the vehicle number…",
    "fetch_vehicle_info": "Checking vehicle and device status…",
    "fault_classifier": "Evaluating the available device evidence…",
    "account_advice": "Checking account and activation status…",
    "create_bug_ticket": "Preparing a software-issue report…",
    "notify_user": "Preparing the support update…",
    "basic_troubleshooting": "Preparing the next troubleshooting step…",
    "recheck_vehicle_info": "Rechecking the latest vehicle status…",
    "select_command": "Selecting the next approved device command…",
    "present_command": "Preparing the command instructions…",
    "process_screenshot": "Reading the diagnostic screenshot…",
    "analyze_output": "Checking diagnostic output against device rules…",
    "diagnosis_result": "Preparing the diagnosis and recommended fix…",
    "resolution_check": "Checking the next resolution step…",
    "resolution_handler": "Updating the issue's resolution status…",
    "human_handoff": "Preparing a support-team handoff…",
    "close_session": "Closing the resolved workflow…",
    "complete_frame": "Updating workflow status…",
    "pause_workflow": "Saving the current step so you can return to it…",
    "resume_workflow": "Restoring the workflow you were working on…",
    "resume_router": "Resuming from the exact pending step…",
    "answer_from_paused": "Checking details from the paused issue…",
    "choose_workflow": "Checking which paused issue you want to continue…",
    "reminder_footer": "Adding the reminder for your paused issue…",
    "recap_node": "Recalling what you asked in this conversation…",
    "save_session": "Saving this conversation…",
}


def progress_label(node_name: str) -> str:
    """Return customer-facing progress copy for a LangGraph node."""
    return _PROGRESS_LABELS.get(node_name, "Working through the next support step…")


def format_sse_event(event: str, payload: dict[str, Any]) -> str:
    """Encode a compact JSON payload as one Server-Sent Event frame."""
    safe_event = "".join(c for c in event if c.isalnum() or c in "_-") or "message"
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return f"event: {safe_event}\ndata: {data}\n\n"


def chunk_text(text: str, chunk_size: int = 28) -> Iterator[str]:
    """Split final text into display chunks without altering whitespace or punctuation."""
    if chunk_size < 1:
        raise ValueError("chunk_size must be greater than zero")
    for start in range(0, len(text), chunk_size):
        yield text[start : start + chunk_size]
