from datetime import datetime, timezone, timedelta
from typing import Any
import uuid

def utcnow() -> datetime: return datetime.now(timezone.utc)
def parse_dt(value: Any) -> datetime | None:
    if not value: return None
    try:
        dt = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError: return None

def summarize_for_prompt(stack: list[dict[str, Any]]) -> str:
    if not stack: return 'No active or paused workflow.'
    lines=[]
    for frame in stack:
        if frame.get('status') in {'active','paused','stale'}:
            lines.append(f"{frame.get('frame_id')} | {frame.get('type')} | {frame.get('status')} | awaiting={frame.get('awaiting')} | step={frame.get('paused_at_step') or frame.get('current_node')}")
    return '\n'.join(lines) or 'No active or paused workflow.'

def pause_active(stack: list[dict[str, Any]], active_frame_id: str | None, paused_at_step: str | None = None) -> tuple[list[dict[str, Any]], None]:
    updated=[dict(f) for f in stack]
    for frame in updated:
        if frame.get('frame_id') == active_frame_id and frame.get('status') == 'active':
            frame['status']='paused'; frame['paused_at']=utcnow().isoformat()
            frame['paused_at_step']=paused_at_step or frame.get('paused_at_step') or f"paused at {frame.get('current_node','the current step')}"
    return updated, None

def push(stack: list[dict[str, Any]], active_frame_id: str | None, workflow_type: str, context: dict[str, Any] | None = None, paused_at_step: str | None = None) -> tuple[list[dict[str, Any]], str]:
    updated, _ = pause_active(stack, active_frame_id, paused_at_step) if active_frame_id else ([dict(f) for f in stack], None)
    frame_id=str(uuid.uuid4())
    frame={'frame_id':frame_id,'type':workflow_type,'status':'active','current_node':None,'awaiting':'none',
        'paused_at_step':None,'paused_at':None,'resume_hint':'Say “continue” to resume this workflow.',
        'context':dict(context or {}),'created_at':utcnow().isoformat(),'updated_at':utcnow().isoformat()}
    updated.append(frame)
    return updated, frame_id

def resume(stack: list[dict[str, Any]], frame_id: str, active_frame_id: str | None = None) -> tuple[list[dict[str, Any]], str | None]:
    updated=[dict(f) for f in stack]
    if active_frame_id and active_frame_id != frame_id:
        updated, _ = pause_active(updated, active_frame_id)
    found=False
    for frame in updated:
        if frame.get('frame_id') == frame_id and frame.get('status') in {'paused','stale','active'}:
            frame['status']='active'; frame['updated_at']=utcnow().isoformat(); found=True
    return updated, frame_id if found else None

def complete(stack: list[dict[str, Any]], frame_id: str | None, outcome: str, summary: str = '') -> list[dict[str, Any]]:
    updated=[]
    for frame in stack:
        item=dict(frame)
        if frame_id and item.get('frame_id') == frame_id:
            item['status'] = 'escalated' if outcome == 'escalated' else 'done'
            item['outcome']=outcome; item['summary']=summary; item['completed_at']=utcnow().isoformat()
        updated.append(item)
    return updated

def expire_stale(stack: list[dict[str, Any]], ttl_minutes: int, max_age_hours: int) -> list[dict[str, Any]]:
    now=utcnow(); updated=[]
    for frame in stack:
        item=dict(frame)
        if item.get('status') == 'paused':
            paused=parse_dt(item.get('paused_at')) or parse_dt(item.get('created_at'))
            if paused:
                age=now-paused
                if age > timedelta(hours=max_age_hours):
                    item['status']='done'; item['outcome']='expired'; item['closed_by']='expiry'
                elif age > timedelta(minutes=ttl_minutes):
                    item['status']='stale'
        updated.append(item)
    return updated
