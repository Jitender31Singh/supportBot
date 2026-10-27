from typing import Any
import logging

logger = logging.getLogger('trackobit_assistant.nodes.resolution_check')

def make_node(runtime):
    def node(state: dict[str, Any]) -> dict[str, Any]:
        session_id = state.get('session_id', '-')
        snap = state.get('vehicle_snapshot') or {}
        fault_cat = state.get('fault_category')
        symptoms = state.get('symptoms') or {}
        user_msg = (
            state.get('dashboard_evidence')
            or symptoms.get('raw_user_message')
            or symptoms.get('summary')
            or state.get('last_user_message')
            or ''
        ).casefold()

        # Check if user had an explicit fault complaint or merely requested configuration/status check
        has_issue_complaint = any(w in user_msg for w in (
            'issue', 'problem', 'not working', 'not updating', 'stale', 'wrong',
            'offline', 'error', 'failed', 'stopped', 'stuck', 'delay', 'delayed',
            'buffer', 'buffering', 'lag', 'lagging', 'slow', 'freeze', 'freezing',
            'glitch', 'unreachable', 'disconnect', 'not showing', 'jumping'
        ))

        vehicle_no = state.get('vehicle_no') or snap.get('vehicle_no', 'your vehicle')
        port = snap.get('port', 'N/A')
        device_type = snap.get('device_type', 'N/A')
        v_status = snap.get('vehicle_status', 'Active')
        d_status = snap.get('device_status', 'Active')
        minutes = snap.get('minutes_since_last_update')
        try:
            minutes_val = float(minutes) if minutes is not None else None
        except (ValueError, TypeError):
            minutes_val = None

        lu_text = f"{minutes_val:.1f} minutes ago (Live)" if minutes_val is not None else "Recent"
        satellites = snap.get('satellites')
        gsm = snap.get('gsm_signals')
        battery = snap.get('battery')

        # Scenario 1: Everything is verified and no issue was found
        if fault_cat == 'no_issue' or state.get('config_step') == 'completed':
            if not has_issue_complaint:
                # User asked to check configuration/status and all checks passed
                logger.info(f"[RESOLUTION_CHECK] No issue reported; presenting verified status summary for {vehicle_no}", extra={'session_id': session_id})
                lines = [
                    f"✅ **Configuration & Status Summary for Vehicle {vehicle_no}**:",
                    f"• **Configured Port**: `{port}` (Confirmed)",
                    f"• **Device Model**: `{device_type}` (Confirmed)",
                    f"• **Vehicle Status**: `{v_status}`",
                    f"• **Device Status**: `{d_status}`",
                    f"• **Last Telemetry Update**: `{lu_text}`",
                ]
                if satellites is not None:
                    lines.append(f"• **GPS Satellites**: `{satellites}`")
                if gsm is not None:
                    lines.append(f"• **GSM Signal**: `{gsm}/5`")
                if battery is not None:
                    lines.append(f"• **Battery**: `{battery}%`")

                lines.append("\nEverything looks fine and the device is communicating properly with the server. No configuration or tracking faults were detected.")
                lines.append("Feel free to ask if you need help with anything else!")
                response = "\n".join(lines)

                return {
                    'response': response,
                    'resolved': True,
                    'awaiting': 'none',
                    'current_step': 'close_session'
                }
            else:
                # User had reported an issue, but telemetry shows current data is live
                logger.info(f"[RESOLUTION_CHECK] Issue reported but current telemetry is fresh for {vehicle_no}", extra={'session_id': session_id})
                response = (
                    f"Vehicle {vehicle_no} is currently updating normally (last update was {lu_text}) "
                    f"and configuration on port {port} ({device_type}) is verified. "
                    "Are you still experiencing any issue on your dashboard? Please answer yes or no."
                )
                return {
                    'response': response,
                    'awaiting': 'resolution_confirm',
                    'paused_at_step': 'waiting for a yes/no resolution confirmation',
                    'current_step': 'resolution_check'
                }

        # Scenario 2: If previous step already set an advice response (e.g. account_advice), preserve it
        existing_resp = state.get('response')
        if existing_resp and 'account' in existing_resp.lower():
            return {
                'response': existing_resp,
                'awaiting': 'resolution_confirm',
                'paused_at_step': 'waiting for resolution confirmation',
                'current_step': 'resolution_check'
            }

        # Scenario 3: Standard troubleshooting follow-up
        return {
            'response': 'Is the tracking issue resolved now? Please answer yes or no.',
            'awaiting': 'resolution_confirm',
            'paused_at_step': 'waiting for a yes/no resolution confirmation',
            'current_step': 'resolution_check'
        }
    return node
