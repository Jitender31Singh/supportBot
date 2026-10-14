"""Thread-safe in-memory session adapter for tests and single-process demos."""
from __future__ import annotations

import copy
import threading
import uuid
from datetime import datetime, timezone
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class MemorySessionStore:
    """In-memory implementation of the SessionStore port; contents are lost on restart."""

    def __init__(self) -> None:
        self._records: dict[str, dict[str, Any]] = {}
        self._lock = threading.RLock()

    def create_session(self) -> dict[str, Any]:
        now = _now()
        sid = str(uuid.uuid4())
        record: dict[str, Any] = {
            "session_id": sid, "title": "New support chat", "created_at": now,
            "updated_at": now, "status": "open", "messages": [],
            "state": {
                "session_id": sid, "active_workflow": "none", "awaiting": "none",
                "symptoms": {}, "vehicle_no": None, "vehicle_snapshot": None,
                "snapshot_history": [], "fault_category": None, "fault_evidence": [],
                "troubleshoot_rounds": 0, "command_history": [], "current_command": None,
                "retry_counters": {}, "ticket_info": None, "resolved": False, "errors": [],
                "dashboard_evidence": None, "screenshot_retry_count": 0,
                "workflow_stack": [], "active_frame_id": None, "pending_resume_frame_id": None,
                "pending_intents": [], "sources": [], "current_step": None,
                "handoff_reason": None, "summary": "",
            },
        }
        with self._lock:
            self._records[sid] = record
        return self._public(record)

    def _public(self, record: dict[str, Any]) -> dict[str, Any]:
        messages = record.get("messages") or []
        state = record.get("state") or {}
        return {
            "session_id": record["session_id"], "title": record.get("title", "Support chat"),
            "created_at": record["created_at"], "updated_at": record["updated_at"],
            "status": record.get("status", "open"), "vehicle_no": state.get("vehicle_no"),
            "last_message": (messages[-1].get("content", "")[:160] if messages else ""),
        }

    def list_sessions(self, user_id: str | None = None) -> list[dict[str, Any]]:
        with self._lock:
            records = [self._public(record) for record in self._records.values()]
        return sorted(records, key=lambda row: row["updated_at"], reverse=True)

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        with self._lock:
            record = self._records.get(session_id)
            return copy.deepcopy(record) if record else None

    def state_for(self, session_id: str) -> dict[str, Any] | None:
        record = self.get_session(session_id)
        if not record:
            return None
        state = dict(record.get("state") or {})
        state["session_id"] = session_id
        return state

    def save_graph_result(self, session_id: str, state: dict[str, Any]) -> None:
        from trackobit_assistant.adapters.serialization import state_to_json
        serialized = state_to_json(state)
        with self._lock:
            if session_id not in self._records:
                raise KeyError(f"Session not found: {session_id}")
            record = self._records[session_id]
            record["messages"] = serialized.pop("messages", record.get("messages", []))
            state_record = record.setdefault("state", {})
            persistent_keys = {
                "active_workflow", "awaiting", "symptoms", "vehicle_no", "vehicle_snapshot",
                "snapshot_history", "fault_category", "fault_evidence", "troubleshoot_rounds",
                "command_history", "current_command", "retry_counters", "ticket_info", "resolved",
                "errors", "dashboard_evidence", "screenshot_retry_count", "workflow_stack",
                "active_frame_id", "current_step", "handoff_reason", "summary", "paused_at_step",
                "pending_resume_frame_id", "sources",
            }
            for key in persistent_keys:
                if key in serialized:
                    state_record[key] = serialized[key]
            user_messages = [message for message in record["messages"] if message.get("role") == "user"]
            if len(user_messages) == 1 and record.get("title") == "New support chat":
                title = (user_messages[0].get("content") or "Support chat").replace("\n", " ").strip()
                record["title"] = title[:39] + ("…" if len(title) > 42 else title[39:42]) if len(title) > 42 else title
            record["updated_at"] = _now()
            if state.get("resolved"):
                record["status"] = "resolved"
            if state.get("active_workflow") == "handoff":
                record["status"] = "escalated"

    def append_message(self, session_id: str, message: dict[str, Any]) -> None:
        with self._lock:
            record = self._records.get(session_id)
            if not record:
                raise KeyError(session_id)
            record.setdefault("messages", []).append(copy.deepcopy(message))
            record["updated_at"] = _now()

    def get_summary(self, session_id: str) -> str:
        record = self.get_session(session_id)
        state = (record or {}).get("state", {})
        return str(state.get("conversation_summary") or state.get("summary", ""))

    def append_attachment_message(self, session_id: str, message: dict[str, Any]) -> None:
        self.append_message(session_id, message)
