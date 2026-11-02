from datetime import datetime
from typing import Any
from trackobit_assistant.schemas.models import FaultCategory, FaultResult, VehicleStateExpectationBucket

# Maps each VehicleStateExpectationBucket to the normalized actual state strings
# that mean "user expectation is already met" (no discrepancy).
_BUCKET_TO_MATCHING_STATES: dict[str, set[str]] = {
    VehicleStateExpectationBucket.STOPPED_STATE:      {'stopped', 'ignition off', 'parked'},
    VehicleStateExpectationBucket.RUNNING_STATE:      {'running', 'moving'},
    VehicleStateExpectationBucket.IDLE_STATE:         {'idle', 'idling'},
    VehicleStateExpectationBucket.OVERSPEED_STATE:    {'overspeed', 'overspeeding'},
    VehicleStateExpectationBucket.UNREACHABLE_STATE:  {'unreachable', 'offline', 'no signal'},
    VehicleStateExpectationBucket.INACTIVE_STATE:     {'inactive', 'dormant'},
    VehicleStateExpectationBucket.NEW_DEVICE_STATE:   {'new', 'unregistered'},
    VehicleStateExpectationBucket.GENERAL_ISSUE_STATE: set(),   # no direct state match — fall through to legacy rules
}


def _normalize_actual_state(snapshot: dict[str, Any]) -> str:
    """Normalize the raw snapshot state string to a canonical lowercase token."""
    raw = str(snapshot.get('state') or '').casefold().strip()
    speed = float(snapshot.get('speed') or 0)

    if 'ignition off' in raw or 'stop' in raw:
        return 'stopped'
    if 'overspeed' in raw:
        return 'overspeed'
    if 'idle' in raw:
        return 'idle'
    if 'run' in raw or speed > 0:
        return 'running'
    if 'unreachable' in raw or 'offline' in raw or 'no signal' in raw:
        return 'unreachable'
    if 'inactive' in raw:
        return 'inactive'
    if 'new' in raw:
        return 'new'
    return raw  # return raw if nothing matched (non-empty) or '' if empty


def classify_fault(
    snapshot: dict[str, Any] | None,
    dashboard_evidence: str | None,
    freshness_threshold_minutes: int = 10,
    state_expectation_bucket: str | None = None,
) -> FaultResult:
    if not snapshot:
        return FaultResult(
            category=FaultCategory.NEED_MORE_INFO,
            confidence=0.3,
            evidence=['Vehicle status is not available yet'],
            needs_user_input=True,
        )
    evidence: list[str] = []

    # ── 1. Account checks (highest priority — always checked first) ──────────
    due = snapshot.get('subscription_due')
    if isinstance(due, str):
        try:
            due_dt = datetime.fromisoformat(due)
        except ValueError:
            due_dt = None
    else:
        due_dt = due
    if due_dt and due_dt.date() < datetime.now(due_dt.tzinfo).date():
        evidence.append('Subscription due date has passed')
        return FaultResult(category=FaultCategory.ACCOUNT_ISSUE, confidence=0.98, evidence=evidence)

    for field in ('vehicle_status', 'device_status'):
        value = snapshot.get(field)
        if value and str(value).casefold() not in {'active', 'true', '1'}:
            evidence.append(f'{field} is {value}')
            return FaultResult(category=FaultCategory.ACCOUNT_ISSUE, confidence=0.95, evidence=evidence)

    # ── 2. State-expectation bucketing (compare user's expected vs actual) ───
    bucket_key = state_expectation_bucket or VehicleStateExpectationBucket.GENERAL_ISSUE_STATE
    matching_states = _BUCKET_TO_MATCHING_STATES.get(bucket_key, set())

    if matching_states:
        actual_state = _normalize_actual_state(snapshot)
        # Check if any of the matching canonical states is a substring of actual_state or vice versa
        state_matches = any(
            ms in actual_state or actual_state in ms
            for ms in matching_states
        )
        evidence.append(f'User expects: {bucket_key} | API actual state: "{snapshot.get("state", "")}" (normalized: "{actual_state}")')

        if state_matches:
            # Backend already reflects the expected state — tell user to refresh
            evidence.append('API state matches user expectation; likely a dashboard display/cache lag')
            return FaultResult(
                category=FaultCategory.NO_ISSUE,
                confidence=0.92,
                evidence=evidence,
            )
        else:
            # Genuine mismatch between what user sees and what API says
            evidence.append('API state does NOT match user expectation — genuine state discrepancy detected')
            return FaultResult(
                category=FaultCategory.STATE_DISCREPANCY,
                confidence=0.90,
                evidence=evidence,
            )

    # ── 3. Legacy deterministic rules (GENERAL_ISSUE_STATE or no bucket) ─────
    minutes = snapshot.get('minutes_since_last_update')
    try:
        minutes = float(minutes) if minutes is not None else None
    except (ValueError, TypeError):
        minutes = None
    state = str(snapshot.get('state') or '').casefold()
    dashboard = (dashboard_evidence or '').casefold()

    if 'overspeed' in state:
        thresh = snapshot.get('overspeed')
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

    if minutes is not None and minutes > freshness_threshold_minutes:
        evidence.append(f'Last update is stale ({minutes:.1f} minutes ago)')
    gsm = snapshot.get('gsm_signals')
    if gsm is not None and int(gsm) <= 1:
        evidence.append(f'Weak GSM signal ({gsm})')
    if snapshot.get('battery_connected') is False:
        evidence.append('Device battery connection is false')
    satellites = snapshot.get('satellites')
    if satellites is not None and int(satellites) < 3:
        evidence.append(f'Low satellite count ({satellites})')
    if evidence:
        return FaultResult(category=FaultCategory.HARDWARE_ISSUE, confidence=0.82, evidence=evidence)
    if not dashboard_evidence:
        return FaultResult(
            category=FaultCategory.NEED_MORE_INFO,
            confidence=0.45,
            evidence=['Need dashboard evidence and/or vehicle movement confirmation'],
            needs_user_input=True,
        )
    return FaultResult(
        category=FaultCategory.UNKNOWN,
        confidence=0.35,
        evidence=['No deterministic rule identified the cause'],
        needs_user_input=True,
    )
