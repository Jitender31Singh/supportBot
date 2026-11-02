"""Bucket-based fault diagnosis node.

Runs after fault_classifier detects a STATE_DISCREPANCY — the user's expected
vehicle state does not match the live telemetry returned by the API.

Architecture
------------
* Each VehicleStateExpectationBucket gets its own top-level handler.
* Each handler examines the *actual* dashboard state (what the user *sees*) and
  the snapshot to decide which diagnostic path to follow.
* Commands are looked up from the YAML command registry via device_command_map,
  so no command string is ever hardcoded here.

ACC field interpretation (after STATUS# command result is parsed)
------------------------------------------------------------------
* acc = 'on'  or acc = '1'  → ignition/ACC detected ON by device
* acc = 'off' or acc = '0'  → ignition/ACC detected OFF by device

LU / SINCE thresholds
---------------------
* lu_minutes  = snapshot['minutes_since_last_update']
* since_minutes = snapshot['hours_since_status'] * 60
* "fresh lu"  → lu_minutes <= LU_THRESHOLD_MINUTES  (device is connected)
* "old since" → since_minutes > SINCE_THRESHOLD_MINUTES  (state has not changed for a long time)

Decision matrix (lu fresh + since old) → device is live but state label is stale/wrong.
"""
from __future__ import annotations

import logging
from typing import Any

from trackobit_assistant.schemas.models import VehicleStateExpectationBucket
from trackobit_assistant.services.device_command_map import (
    get_status_command,
    describe_status_command,
)

logger = logging.getLogger('trackobit_assistant.nodes.fault_diagnosis')

# ── thresholds ────────────────────────────────────────────────────────────────
LU_THRESHOLD_MINUTES    = 10    # last update fresher than this → device is communicating
SINCE_THRESHOLD_MINUTES = 30    # state unchanged longer than this → state may be stale


# ── snapshot helpers ──────────────────────────────────────────────────────────

def _lu_minutes(snapshot: dict) -> float | None:
    v = snapshot.get('minutes_since_last_update')
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _since_minutes(snapshot: dict) -> float | None:
    v = snapshot.get('hours_since_status')
    try:
        return float(v) * 60.0
    except (TypeError, ValueError):
        return None


def _lu_is_fresh(snapshot: dict) -> bool:
    lu = _lu_minutes(snapshot)
    return lu is not None and lu <= LU_THRESHOLD_MINUTES


def _since_is_old(snapshot: dict) -> bool:
    since = _since_minutes(snapshot)
    return since is not None and since > SINCE_THRESHOLD_MINUTES


def _acc_is_on(parsed_output: dict | None) -> bool | None:
    """
    Return True  → ACC = 1/on (ignition detected ON)
    Return False → ACC = 0/off (ignition detected OFF)
    Return None  → ACC field not present in parsed output
    """
    if not parsed_output:
        return None
    acc_val = parsed_output.get('acc')
    if acc_val is None:
        return None
    return acc_val in {'1', 'on'}


def _device_type(state: dict) -> str:
    snapshot = state.get('vehicle_snapshot') or {}
    return (
        snapshot.get('device_type')
        or (state.get('symptoms') or {}).get('device_type_mention')
        or ''
    )


def _vehicle_no(state: dict) -> str:
    snapshot = state.get('vehicle_snapshot') or {}
    return state.get('vehicle_no') or snapshot.get('vehicle_no', 'the vehicle')


# ── shared response builders ──────────────────────────────────────────────────

def _ask_for_status_command(
    vehicle_no: str,
    device_type: str,
    runtime,
    context_message: str = '',
) -> dict[str, Any]:
    """Ask user to send the STATUS# (or equivalent) command and share screenshot."""
    cmd = get_status_command(device_type, runtime.command_registry) if runtime.command_registry else None
    instruction = describe_status_command(cmd, device_type)
    response = (
        f"{context_message}\n\n"
        f"To diagnose the issue with vehicle **{vehicle_no}**, I need the live device status output.\n\n"
        f"{instruction}\n\n"
        f"Once you have the reply, attach a clear screenshot or paste the text here."
    ).strip()
    return {
        'response': response,
        'current_command': cmd.model_dump(mode='json') if cmd else None,
        'command_available': cmd is not None,
        'awaiting': 'command_screenshot',
        'paused_at_step': f"waiting for {cmd.command if cmd else 'device status command'} reply screenshot",
        'current_step': 'fault_diagnosis',
        'next_diagnosis_step': 'process_screenshot',
    }


def _ignition_wiring_advice(vehicle_no: str) -> str:
    return (
        f"The device on vehicle **{vehicle_no}** reports ACC (ignition) as **ON** even though the vehicle is "
        f"physically stopped. This indicates a **wiring issue** — the ACC wire is picking up a false signal.\n\n"
        f"**Options**:\n"
        f"1. **Fix the wiring**: Have an authorised technician inspect and correct the ACC/ignition wire connection.\n"
        f"2. **Temporary workaround**: In the TrackoBit vehicle page, enable the checkbox "
        f"**'Ignition wire not connected'** — this will stop the device from using the ACC wire "
        f"for state detection until the wiring is corrected."
    )


def _escalate_to_support(vehicle_no: str, reason: str) -> dict[str, Any]:
    return {
        'response': (
            f"The device status command for vehicle **{vehicle_no}** shows ACC **OFF** (ignition not detected), "
            f"but the dashboard state does not match the physical reality. This suggests a platform-level issue "
            f"rather than a wiring fault.\n\n"
            f"Reason: {reason}\n\n"
            f"I am escalating this to our support team with all collected diagnostics."
        ),
        'awaiting': 'none',
        'current_step': 'human_handoff',
        'next_diagnosis_step': 'human_handoff',
        'handoff_reason': 'state_discrepancy_acc_off',
    }


# ── STOPPED_STATE handlers ────────────────────────────────────────────────────

def _stopped__actual_running(
    snapshot: dict, vehicle_no: str, actual_state: str,
    state: dict, runtime,
) -> dict[str, Any]:
    """
    Dashboard shows RUNNING/OVERSPEED but user says vehicle is STOPPED.
    Step 1: Check lu/since. If lu fresh + since old → likely ACC wiring or buffering.
             Ask for STATUS# → check ACC field.
    """
    lu   = _lu_minutes(snapshot)
    since = _since_minutes(snapshot)
    lu_fresh   = _lu_is_fresh(snapshot)
    since_old  = _since_is_old(snapshot)

    # Check if we already have STATUS# output and ACC field
    parsed_output = state.get('parsed_command_output') or {}
    acc = _acc_is_on(parsed_output)

    if acc is not None:
        # We have the STATUS# result — make a decision
        if acc:  # ACC=ON → device thinks ignition is on → wiring issue
            return {
                'response': _ignition_wiring_advice(vehicle_no),
                'awaiting': 'none',
                'current_step': 'fault_diagnosis',
                'next_diagnosis_step': 'resolution_check',
            }
        else:  # ACC=OFF → wiring seems fine → escalate
            return _escalate_to_support(
                vehicle_no,
                "Device reports ACC=OFF but dashboard still shows running state."
            )

    # No STATUS# output yet — check lu/since and ask for command
    if lu_fresh and since_old:
        context = (
            f"Vehicle **{vehicle_no}** is physically stopped, but the dashboard shows it as "
            f"**{actual_state}**. The device last communicated **{lu:.1f} minutes ago** (live), "
            f"but its state has been **{actual_state}** for over {since:.0f} minutes. "
            f"This often indicates a false ACC/ignition wire signal."
        )
    elif lu_fresh and not since_old:
        context = (
            f"Vehicle **{vehicle_no}** is physically stopped but dashboard shows **{actual_state}**. "
            f"The device is actively communicating (last update {lu:.1f} min ago). "
            f"A GPS drift or buffered packet could be the cause, but we need to check the device state."
        )
    else:
        # Stale lu — possibly buffering old movement packets
        lu_str = f"{lu:.1f} minutes" if lu is not None else "unknown"
        context = (
            f"Vehicle **{vehicle_no}** is physically stopped but dashboard shows **{actual_state}**. "
            f"The device last updated {lu_str} ago — it may still be flushing old movement packets "
            f"recorded before the vehicle stopped."
        )

    device_type = _device_type(state)
    return _ask_for_status_command(vehicle_no, device_type, runtime, context)


def _stopped__actual_unreachable(
    snapshot: dict, vehicle_no: str, state: dict, runtime,
) -> dict[str, Any]:
    """Dashboard shows UNREACHABLE but user says vehicle is stopped (expected)."""
    lu    = _lu_minutes(snapshot)
    since = _since_minutes(snapshot)
    lu_str    = f"{lu:.1f} minutes ago"    if lu    is not None else "an unknown time ago"
    since_str = f"{since:.0f} minutes"    if since  is not None else "unknown duration"

    if _lu_is_fresh(snapshot) and _since_is_old(snapshot):
        # Device is talking but has been in unreachable state for a long time → escalate
        return _escalate_to_support(
            vehicle_no,
            f"Device is communicating (lu={lu_str}) but has been unreachable for {since_str}. "
            "Platform state may not have refreshed correctly."
        )
    # lu is stale → connectivity issue
    return {
        'response': (
            f"Vehicle **{vehicle_no}** is showing as **Unreachable** on the dashboard. "
            f"The device last communicated {lu_str}. "
            f"The current state has been unreachable for {since_str}.\n\n"
            f"**Recommended steps**:\n"
            f"1. Check that the vehicle has power and the ignition is accessible.\n"
            f"2. Move the vehicle to an open area with good mobile network coverage.\n"
            f"3. Let it sit for 5 minutes, then reply *done* so I can fetch a fresh status."
        ),
        'awaiting': 'troubleshoot_result',
        'paused_at_step': 'waiting for user to move vehicle to network area',
        'current_step': 'fault_diagnosis',
        'next_diagnosis_step': 'recheck_vehicle_info',
    }


def _diagnose_stopped_state(state: dict, runtime) -> dict[str, Any]:
    """
    User expects STOPPED_STATE.
    Route based on what the API actually shows (actual_vehicle_state).
    """
    snapshot      = state.get('vehicle_snapshot') or {}
    vehicle_no    = _vehicle_no(state)
    actual_state  = (state.get('actual_vehicle_state') or '').casefold()

    if actual_state in {'running', 'moving', 'overspeed', 'overspeeding', 'idle', 'idling'}:
        return _stopped__actual_running(snapshot, vehicle_no, actual_state, state, runtime)

    if actual_state in {'unreachable', 'offline', 'no signal'}:
        return _stopped__actual_unreachable(snapshot, vehicle_no, state, runtime)

    # inactive / new / unknown — not implementing per spec
    return {
        'response': (
            f"Vehicle **{vehicle_no}** is showing an unexpected state on the dashboard (`{actual_state}`). "
            f"Please share a screenshot of the vehicle's current dashboard view so our team can investigate."
        ),
        'awaiting': 'dashboard_evidence',
        'paused_at_step': 'waiting for dashboard screenshot',
        'current_step': 'fault_diagnosis',
        'next_diagnosis_step': 'update_dashboard_evidence',
    }


# ── RUNNING_STATE handlers ────────────────────────────────────────────────────

def _running__actual_stopped(
    snapshot: dict, vehicle_no: str, state: dict, runtime,
) -> dict[str, Any]:
    """
    Dashboard shows STOPPED but user says vehicle is RUNNING.
    lu fresh + since old → likely ACC not detected → ask STATUS# → check ACC.
    """
    lu   = _lu_minutes(snapshot)
    since = _since_minutes(snapshot)
    lu_fresh  = _lu_is_fresh(snapshot)
    since_old = _since_is_old(snapshot)

    parsed_output = state.get('parsed_command_output') or {}
    acc = _acc_is_on(parsed_output)

    if acc is not None:
        if not acc:  # ACC=OFF → device not detecting ignition → wiring problem
            return {
                'response': (
                    f"The device on vehicle **{vehicle_no}** reports ACC (ignition) as **OFF**, "
                    f"but you say the vehicle is currently running. "
                    f"This means the device is **not detecting the ignition signal** — a wiring issue.\n\n"
                    f"**Options**:\n"
                    f"1. **Fix the wiring**: Have an authorised technician inspect the ACC/ignition wire.\n"
                    f"2. **Temporary workaround**: In the TrackoBit vehicle page, check "
                    f"**'Ignition wire not connected'** — the device will then use GPS motion "
                    f"to detect movement instead of the ACC wire."
                ),
                'awaiting': 'none',
                'current_step': 'fault_diagnosis',
                'next_diagnosis_step': 'resolution_check',
            }
        else:  # ACC=ON but still showing stopped → escalate
            return _escalate_to_support(
                vehicle_no,
                "Device reports ACC=ON (ignition detected) but dashboard still shows stopped."
            )

    if lu_fresh and since_old:
        context = (
            f"Vehicle **{vehicle_no}** is running, but the dashboard shows it as **Stopped**. "
            f"The device communicated **{lu:.1f} minutes ago** (live) but has been in Stopped state "
            f"for over {since:.0f} minutes. The device may not be detecting the ignition signal."
        )
    else:
        lu_str = f"{lu:.1f} minutes" if lu is not None else "unknown"
        context = (
            f"Vehicle **{vehicle_no}** is running but showing as **Stopped**. "
            f"Last device update was {lu_str} ago. "
            f"Let me check whether the device is detecting the ignition."
        )

    device_type = _device_type(state)
    return _ask_for_status_command(vehicle_no, device_type, runtime, context)


def _running__actual_overspeed(
    snapshot: dict, vehicle_no: str,
) -> dict[str, Any]:
    """Dashboard shows OVERSPEED — check speed vs configured threshold."""
    speed     = snapshot.get('speed') or 0
    threshold = snapshot.get('speeding_threshold') or snapshot.get('overspeed')
    try:
        s_val = float(speed)
        t_val = float(threshold) if threshold is not None else None
    except (TypeError, ValueError):
        s_val = 0.0
        t_val = None

    if t_val is not None:
        if s_val > t_val:
            finding = (
                f"Vehicle speed ({s_val:.0f} km/h) exceeds the configured overspeed limit "
                f"({t_val:.0f} km/h) — the **Overspeed** label is correct."
            )
            advice = (
                f"The vehicle **{vehicle_no}** was indeed overspeeding when the state was recorded. "
                f"If the vehicle has since slowed down, the state will refresh on the next packet. "
                f"You may wish to review the driver's speed and the configured limit in TrackoBit settings."
            )
        else:
            finding = (
                f"Vehicle speed ({s_val:.0f} km/h) is within the configured overspeed limit "
                f"({t_val:.0f} km/h) — the Overspeed state appears **incorrect**."
            )
            advice = (
                f"This looks like a stale overspeed flag on vehicle **{vehicle_no}**. "
                f"The state should clear on the next telemetry packet. "
                f"If it persists after a few minutes, please contact support."
            )
    else:
        finding = f"No overspeed threshold is configured on vehicle **{vehicle_no}**."
        advice = (
            "The Overspeed state may have been triggered by a previous limit that is no longer set. "
            "Please check the vehicle's speed alert configuration in TrackoBit."
        )

    return {
        'response': f"{finding}\n\n{advice}",
        'awaiting': 'none',
        'current_step': 'fault_diagnosis',
        'next_diagnosis_step': 'resolution_check',
    }


def _running__actual_unreachable(
    snapshot: dict, vehicle_no: str,
) -> dict[str, Any]:
    """Dashboard shows UNREACHABLE but user says vehicle is running."""
    lu    = _lu_minutes(snapshot)
    lu_str = f"{lu:.1f} minutes" if lu is not None else "unknown"

    return {
        'response': (
            f"Vehicle **{vehicle_no}** is running but the dashboard shows it as **Unreachable** "
            f"(last update {lu_str} ago).\n\n"
            f"**Recommended steps**:\n"
            f"1. Drive to an open area with strong mobile network signal.\n"
            f"2. Let the vehicle run for 3–5 minutes.\n"
            f"3. Reply *done* and I'll fetch a fresh status to confirm connectivity is restored."
        ),
        'awaiting': 'troubleshoot_result',
        'paused_at_step': 'waiting for user to move to network area and report back',
        'current_step': 'fault_diagnosis',
        'next_diagnosis_step': 'recheck_vehicle_info',
    }


def _running__actual_new(
    snapshot: dict, vehicle_no: str,
) -> dict[str, Any]:
    """Dashboard shows NEW — check address field to confirm server connection."""
    address = (snapshot.get('address') or '').casefold()
    connected = 'connected' in address or bool(snapshot.get('logger'))

    if connected:
        return {
            'response': (
                f"Vehicle **{vehicle_no}** is showing as **New** but the server has received a connection. "
                f"The live state will update shortly as the device sends its first valid GPS packet.\n\n"
                f"Please wait 5–10 minutes in an open area with good mobile signal, "
                f"then refresh the TrackoBit dashboard."
            ),
            'awaiting': 'none',
            'current_step': 'fault_diagnosis',
            'next_diagnosis_step': 'resolution_check',
        }
    else:
        return {
            'response': (
                f"Vehicle **{vehicle_no}** is showing as **New** and the server has not yet received "
                f"a confirmed connection from the device.\n\n"
                f"**Steps to complete setup**:\n"
                f"1. Power on the vehicle in an open area with mobile network coverage.\n"
                f"2. Confirm the device model and port are correctly configured in TrackoBit.\n"
                f"3. Wait 5–10 minutes for the first packet.\n\n"
                f"Reply *done* once the vehicle is powered on and I'll check for a first packet."
            ),
            'awaiting': 'troubleshoot_result',
            'paused_at_step': 'waiting for user to power on and confirm first connection',
            'current_step': 'fault_diagnosis',
            'next_diagnosis_step': 'recheck_vehicle_info',
        }


def _diagnose_running_state(state: dict, runtime) -> dict[str, Any]:
    """User expects RUNNING_STATE. Route based on actual API state."""
    snapshot     = state.get('vehicle_snapshot') or {}
    vehicle_no   = _vehicle_no(state)
    actual_state = (state.get('actual_vehicle_state') or '').casefold()

    if actual_state in {'stopped', 'ignition off', 'parked'}:
        return _running__actual_stopped(snapshot, vehicle_no, state, runtime)

    if actual_state in {'overspeed', 'overspeeding'}:
        return _running__actual_overspeed(snapshot, vehicle_no)

    if actual_state in {'unreachable', 'offline', 'no signal'}:
        return _running__actual_unreachable(snapshot, vehicle_no)

    if actual_state in {'new', 'unregistered'}:
        return _running__actual_new(snapshot, vehicle_no)

    # idle or unknown
    return {
        'response': (
            f"Vehicle **{vehicle_no}** shows **{actual_state}** but you say it is running. "
            f"Please share a screenshot of the current dashboard view so I can investigate."
        ),
        'awaiting': 'dashboard_evidence',
        'paused_at_step': 'waiting for dashboard screenshot',
        'current_step': 'fault_diagnosis',
        'next_diagnosis_step': 'update_dashboard_evidence',
    }


# ── UNREACHABLE_STATE handler ─────────────────────────────────────────────────

def _diagnose_unreachable_state(state: dict) -> dict[str, Any]:
    """
    User expects the device to be reachable but dashboard shows UNREACHABLE.
    lu fresh + since old → server issue → escalate.
    lu stale → connectivity → ask to come to network.
    """
    snapshot   = state.get('vehicle_snapshot') or {}
    vehicle_no = _vehicle_no(state)
    lu         = _lu_minutes(snapshot)
    since      = _since_minutes(snapshot)
    lu_str     = f"{lu:.1f} minutes ago"  if lu    is not None else "an unknown time"
    since_str  = f"{since:.0f} minutes"   if since is not None else "unknown duration"

    if _lu_is_fresh(snapshot) and _since_is_old(snapshot):
        return _escalate_to_support(
            vehicle_no,
            f"Device is communicating (lu={lu_str}) but has been in unreachable state for {since_str}. "
            "This is likely a server-side state refresh issue."
        )

    return {
        'response': (
            f"Vehicle **{vehicle_no}** is showing as **Unreachable**. "
            f"Last device communication: {lu_str}. "
            f"Device has been in this state for: {since_str}.\n\n"
            f"**Recommended steps**:\n"
            f"1. Check that the vehicle has power (ignition accessible).\n"
            f"2. Move to an open area with strong mobile network coverage.\n"
            f"3. Let the device run for 3–5 minutes.\n"
            f"4. Reply *done* and I'll pull a fresh status to confirm."
        ),
        'awaiting': 'troubleshoot_result',
        'paused_at_step': 'waiting for user to move to network area and confirm',
        'current_step': 'fault_diagnosis',
        'next_diagnosis_step': 'recheck_vehicle_info',
    }


# ── stubs for unimplemented buckets ───────────────────────────────────────────

def _stub_not_implemented(bucket: str, vehicle_no: str) -> dict[str, Any]:
    logger.info(f"[FAULT_DIAGNOSIS] Bucket '{bucket}' not yet implemented — collecting dashboard evidence")
    return {
        'response': (
            f"I'm investigating the state discrepancy for vehicle **{vehicle_no}** "
            f"(expected: {bucket.replace('_', ' ')}).\n\n"
            f"To help me diagnose this accurately, could you share a screenshot of the current "
            f"TrackoBit dashboard view for this vehicle?"
        ),
        'awaiting': 'dashboard_evidence',
        'paused_at_step': 'waiting for dashboard screenshot',
        'current_step': 'fault_diagnosis',
        'next_diagnosis_step': 'update_dashboard_evidence',
    }


# ── main node ─────────────────────────────────────────────────────────────────

def make_node(runtime):
    def node(state: dict[str, Any]) -> dict[str, Any]:
        session_id   = state.get('session_id', '-')
        vehicle_no   = _vehicle_no(state)
        bucket       = state.get('state_expectation_bucket') or (
            (state.get('symptoms') or {}).get('state_expectation_bucket')
        )
        actual_state = state.get('actual_vehicle_state', 'unknown')

        logger.info(
            f"[FAULT_DIAGNOSIS] bucket='{bucket}', actual_state='{actual_state}', vehicle='{vehicle_no}'",
            extra={'session_id': session_id}
        )

        match bucket:
            case VehicleStateExpectationBucket.STOPPED_STATE:
                result = _diagnose_stopped_state(state, runtime)

            case VehicleStateExpectationBucket.RUNNING_STATE:
                result = _diagnose_running_state(state, runtime)

            case VehicleStateExpectationBucket.UNREACHABLE_STATE:
                result = _diagnose_unreachable_state(state)

            case VehicleStateExpectationBucket.IDLE_STATE:
                # Not implementing per spec
                result = _stub_not_implemented(VehicleStateExpectationBucket.IDLE_STATE, vehicle_no)

            case VehicleStateExpectationBucket.OVERSPEED_STATE:
                # Not implementing per spec
                result = _stub_not_implemented(VehicleStateExpectationBucket.OVERSPEED_STATE, vehicle_no)

            case VehicleStateExpectationBucket.INACTIVE_STATE:
                # Not implementing per spec
                result = _stub_not_implemented(VehicleStateExpectationBucket.INACTIVE_STATE, vehicle_no)

            case VehicleStateExpectationBucket.NEW_DEVICE_STATE:
                # Not implementing per spec
                result = _stub_not_implemented(VehicleStateExpectationBucket.NEW_DEVICE_STATE, vehicle_no)

            case _:
                # GENERAL_ISSUE_STATE or unrecognised — fall back to basic troubleshooting
                logger.info(
                    f"[FAULT_DIAGNOSIS] No specific bucket matched (bucket='{bucket}'); "
                    f"falling back to basic_troubleshooting",
                    extra={'session_id': session_id}
                )
                result = {
                    'response': '',
                    'awaiting': 'none',
                    'current_step': 'basic_troubleshooting',
                    'next_diagnosis_step': 'basic_troubleshooting',
                }

        rounds = int(state.get('troubleshoot_rounds') or 0) + 1
        return {**result, 'troubleshoot_rounds': rounds}

    return node
