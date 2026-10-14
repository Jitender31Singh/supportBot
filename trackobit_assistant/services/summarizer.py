from typing import Any

def summarize_session(state: dict[str, Any]) -> str:
    parts=[]
    if state.get('vehicle_no'): parts.append(f"Vehicle: {state['vehicle_no']}")
    if state.get('symptoms', {}).get('summary'): parts.append(f"Issue: {state['symptoms']['summary']}")
    if state.get('fault_category'): parts.append(f"Classification: {state['fault_category']}")
    if state.get('fault_evidence'): parts.append('Evidence: ' + '; '.join(map(str, state['fault_evidence'])))
    snap=state.get('vehicle_snapshot') or {}
    if snap: parts.append(f"Device: {snap.get('device_type')}; last update: {snap.get('last_update')}; state: {snap.get('state')}")
    for item in state.get('command_history') or []:
        parts.append(f"Command {item.get('command')} => {item.get('verdict')}: {item.get('finding')}")
    if state.get('ticket_info'): parts.append(f"Ticket: {state['ticket_info'].get('ticket_id')}")
    return '\n'.join(parts) if parts else 'No diagnostic details have been collected yet.'
