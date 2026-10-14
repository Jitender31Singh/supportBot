import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

ROLE_TO_CLASS = {'user': HumanMessage, 'assistant': AIMessage, 'system': SystemMessage, 'tool': ToolMessage}

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()

def message_to_dict(message: Any) -> dict[str, Any]:
    if isinstance(message, HumanMessage): role = 'user'
    elif isinstance(message, AIMessage): role = 'assistant'
    elif isinstance(message, SystemMessage): role = 'system'
    elif isinstance(message, ToolMessage): role = 'tool'
    else: role = 'assistant'
    content = message.content
    if not isinstance(content, str): content = str(content)
    return {'id': message.id or str(uuid.uuid4()), 'role': role, 'content': content, 'created_at': utc_now(), 'attachment_name': None}

def dict_to_message(row: dict[str, Any]):
    cls = ROLE_TO_CLASS.get(row.get('role', 'user'), HumanMessage)
    return cls(content=row.get('content', ''), id=row.get('id') or str(uuid.uuid4()))

class JsonSessionStore:
    """Small local JSON session adapter. Replace this adapter for a shared production database."""
    def __init__(self, directory: Path):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def _path(self, session_id: str) -> Path:
        # Avoid allowing user-controlled path fragments.
        safe_id = ''.join(c for c in session_id if c.isalnum() or c in '-_')
        return self.directory / f'{safe_id}.json'

    def create_session(self) -> dict[str, Any]:
        now = utc_now()
        record = {
            'session_id': str(uuid.uuid4()), 'title': 'New support chat', 'created_at': now,
            'updated_at': now, 'status': 'open', 'messages': [], 'state': {
                'session_id': None, 'active_workflow': 'none', 'awaiting': 'none',
                'symptoms': {}, 'vehicle_no': None, 'vehicle_snapshot': None,
                'snapshot_history': [], 'fault_category': None, 'fault_evidence': [],
                'troubleshoot_rounds': 0, 'command_history': [], 'current_command': None,
                'retry_counters': {}, 'ticket_info': None, 'resolved': False, 'errors': [],
                'dashboard_evidence': None, 'screenshot_retry_count': 0,
                'workflow_stack': [], 'active_frame_id': None, 'pending_resume_frame_id': None, 'pending_intents': [],
                'sources': [], 'current_step': None, 'handoff_reason': None, 'summary': '',
                'conversation_summary': '', 'summary_message_count': 0,
            }
        }
        record['state']['session_id'] = record['session_id']
        with self._lock:
            self._write(record)
        return self._public(record)

    def _write(self, record: dict[str, Any]) -> None:
        path = self._path(record['session_id'])
        tmp = path.with_suffix('.tmp')
        tmp.write_text(json.dumps(record, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
        tmp.replace(path)

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        path = self._path(session_id)
        if not path.exists(): return None
        with self._lock:
            try: return json.loads(path.read_text(encoding='utf-8'))
            except (json.JSONDecodeError, OSError): return None

    def _public(self, record: dict[str, Any]) -> dict[str, Any]:
        state = record.get('state') or {}
        msgs = record.get('messages') or []
        return {
            'session_id': record['session_id'], 'title': record.get('title', 'Support chat'),
            'created_at': record['created_at'], 'updated_at': record['updated_at'],
            'status': record.get('status', 'open'), 'vehicle_no': state.get('vehicle_no'),
            'last_message': msgs[-1].get('content', '')[:160] if msgs else '',
        }

    def list_sessions(self, user_id: str | None = None) -> list[dict[str, Any]]:
        rows = []
        with self._lock:
            for path in self.directory.glob('*.json'):
                try:
                    rec = json.loads(path.read_text(encoding='utf-8'))
                    rows.append(self._public(rec))
                except (json.JSONDecodeError, OSError):
                    continue
        return sorted(rows, key=lambda r: r['updated_at'], reverse=True)

    def save_graph_result(self, session_id: str, state: dict[str, Any]) -> None:
        with self._lock:
            rec = self.get_session(session_id)
            if not rec: raise KeyError(f'Session not found: {session_id}')
            from trackobit_assistant.adapters.serialization import state_to_json
            serial = state_to_json(state)
            # Transcript is sourced from LangGraph messages, retaining stable message IDs.
            rec['messages'] = serial.pop('messages', rec.get('messages', []))
            persistent_keys = {
                'active_workflow', 'awaiting', 'symptoms', 'vehicle_no', 'vehicle_snapshot', 'snapshot_history',
                'fault_category', 'fault_evidence', 'troubleshoot_rounds', 'command_history', 'current_command',
                'retry_counters', 'ticket_info', 'resolved', 'errors', 'dashboard_evidence', 'screenshot_retry_count',
                'workflow_stack', 'active_frame_id', 'current_step', 'handoff_reason', 'summary', 'conversation_summary',
                'summary_message_count', 'paused_at_step', 'pending_resume_frame_id',
            }
            state_record = rec.setdefault('state', {})
            for key in persistent_keys:
                if key in serial:
                    state_record[key] = serial[key]
            user_messages = [m for m in rec['messages'] if m.get('role') == 'user']
            if len(user_messages) == 1 and rec.get('title') == 'New support chat':
                rec['title'] = (user_messages[0].get('content') or 'Support chat').strip().replace('\n', ' ')[:42]
                if len((user_messages[0].get('content') or '')) > 42: rec['title'] = rec['title'].rstrip() + '…'
            rec['updated_at'] = utc_now()
            if state.get('resolved'):
                rec['status'] = 'resolved'
            if state.get('active_workflow') == 'handoff':
                rec['status'] = 'escalated'
            self._write(rec)

    def state_for(self, session_id: str) -> dict[str, Any] | None:
        rec = self.get_session(session_id)
        if not rec: return None
        state = dict(rec.get('state') or {})
        state['session_id'] = session_id
        return state

    def append_attachment_message(self, session_id: str, message: dict[str, Any]) -> None:
        """Utility for explicit attachment-only turns or failure recovery."""
        with self._lock:
            rec = self.get_session(session_id)
            if not rec: raise KeyError(session_id)
            rec.setdefault('messages', []).append(message)
            rec['updated_at'] = utc_now()
            self._write(rec)
    def append_message(self, session_id: str, message: dict[str, Any]) -> None:
        """Append a UI/API message through the adapter interface."""
        with self._lock:
            rec = self.get_session(session_id)
            if not rec:
                raise KeyError(session_id)
            rec.setdefault('messages', []).append(message)
            rec['updated_at'] = utc_now()
            self._write(rec)

    def get_summary(self, session_id: str) -> str:
        rec = self.get_session(session_id)
        state = (rec or {}).get('state', {})
        return str(state.get('conversation_summary') or state.get('summary', ''))

    def load(self, session_id: str) -> dict[str, Any] | None:
        return self.state_for(session_id)

    def save(self, session_id: str, state: dict[str, Any]) -> None:
        self.save_graph_result(session_id, state)

    def list_sessions_for_user(self, user_id: str | None = None) -> list[dict[str, Any]]:
        # Authentication/user ownership is intentionally not fabricated in the local demo.
        # The optional user ID is accepted to keep the production port extension straightforward.
        return self.list_sessions()

