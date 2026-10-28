from datetime import datetime
from typing import Any
from trackobit_assistant.schemas.models import FaultCategory, FaultResult

def classify_fault(snapshot: dict[str, Any] | None, dashboard_evidence: str | None, freshness_threshold_minutes: int = 10) -> FaultResult:
    if not snapshot:
        return FaultResult(category=FaultCategory.NEED_MORE_INFO, confidence=0.3, evidence=['Vehicle status is not available yet'], needs_user_input=True)
    evidence: list[str] = []
    due = snapshot.get('subscription_due')
    if isinstance(due, str):
        try: due_dt = datetime.fromisoformat(due)
        except ValueError: due_dt = None
    else: due_dt = due
    if due_dt and due_dt.date() < datetime.now(due_dt.tzinfo).date():
        evidence.append('Subscription due date has passed')
        return FaultResult(category=FaultCategory.ACCOUNT_ISSUE, confidence=0.98, evidence=evidence)
    for field in ('vehicle_status', 'device_status'):
        value = snapshot.get(field)
        if value and str(value).casefold() not in {'active', 'true', '1'}:
            evidence.append(f'{field} is {value}')
            return FaultResult(category=FaultCategory.ACCOUNT_ISSUE, confidence=0.95, evidence=evidence)
    if snapshot.get('logger') is False:
        evidence.append('Device logger is disabled')
        return FaultResult(category=FaultCategory.ACCOUNT_ISSUE, confidence=0.9, evidence=evidence)
    minutes = snapshot.get('minutes_since_last_update')
    try: minutes = float(minutes) if minutes is not None else None
    except (ValueError, TypeError): minutes = None
    state = str(snapshot.get('state') or '').casefold()
    dashboard = (dashboard_evidence or '').casefold()

    if 'overspeed' in state:
        thresh = snapshot.get('speeding_threshold') or snapshot.get('speedingThreshold') or snapshot.get('speedLimit')
        speed = snapshot.get('speed')
        if thresh is not None and speed is not None:
            try:
                t_val = float(thresh)
                s_val = float(speed)
                if s_val > t_val:
                    evidence.append(f'Vehicle speed ({s_val} km/h) exceeds configured speeding threshold ({t_val} km/h)')
                    return FaultResult(category=FaultCategory.NO_ISSUE, confidence=0.85, evidence=evidence)
                else:
                    evidence.append(f'Vehicle state is overspeeding but speed ({s_val} km/h) is within threshold ({t_val} km/h)')
                    return FaultResult(category=FaultCategory.SOFTWARE_ISSUE, confidence=0.88, evidence=evidence)
            except (ValueError, TypeError):
                pass
    if minutes is not None and minutes <= freshness_threshold_minutes:
        evidence.append(f'API has a fresh update ({minutes:.1f} minutes ago)')
        software_terms = (
            'stale', 'wrong', 'not updating', 'old location', 'dashboard', 'buffer', 'buffering',
            'lag', 'lagging', 'delay', 'delayed', 'slow', 'freeze', 'freezing', 'stuck',
            'loading', 'jumping', 'glitch', 'unreachable', 'app', 'portal', 'web', 'screen', 'ui', 'map', 'not showing'
        )
        if any(word in dashboard for word in software_terms):
            evidence.append('User reports dashboard/app data is stale, buffering, or incorrect despite live telemetry')
            return FaultResult(category=FaultCategory.SOFTWARE_ISSUE, confidence=0.88, evidence=evidence)
        if not dashboard_evidence or any(p in dashboard for p in ('check', 'status', 'config', 'details', 'info', 'view', 'look', 'read')):
            return FaultResult(category=FaultCategory.NO_ISSUE, confidence=0.70, evidence=evidence + ['Configuration and telemetry verified'])
        evidence.append(f'Unresolved user observation on live device: {dashboard[:80]}')
        return FaultResult(category=FaultCategory.SOFTWARE_ISSUE, confidence=0.75, evidence=evidence)
    if ('ignition off' in state or snapshot.get('parked') is True) and (minutes is None or minutes > freshness_threshold_minutes):
        evidence.append('Last status says ignition off/parked; a stale update alone does not prove a device fault')
        return FaultResult(category=FaultCategory.PARKED_IGNITION_OFF, confidence=0.84, evidence=evidence, needs_user_input=True)
    if minutes is not None and minutes > freshness_threshold_minutes:
        evidence.append(f'Last update is stale ({minutes:.1f} minutes ago)')
    gsm = snapshot.get('gsm_signals')
    if gsm is not None and int(gsm) <= 1: evidence.append(f'Weak GSM signal ({gsm})')
    if snapshot.get('battery_connected') is False: evidence.append('Device battery connection is false')
    satellites = snapshot.get('satellites')
    if satellites is not None and int(satellites) < 3: evidence.append(f'Low satellite count ({satellites})')
    if evidence:
        return FaultResult(category=FaultCategory.HARDWARE_ISSUE, confidence=0.82, evidence=evidence)
    if not dashboard_evidence:
        return FaultResult(category=FaultCategory.NEED_MORE_INFO, confidence=0.45, evidence=['Need dashboard evidence and/or vehicle movement confirmation'], needs_user_input=True)
    return FaultResult(category=FaultCategory.UNKNOWN, confidence=0.35, evidence=['No deterministic rule identified the cause'], needs_user_input=True)
