"""Check configuration node for vehicle and device validation before fault classification.

Follows support procedures:
1. Pre-flight checks (from API): lu, subscriptionDue, subscriptionStart must not be empty;
   deviceType, imei, port must be configured (ask user to fix and re-check if missing);
   vehicleStatus must be Active (check subscription expiry if not).
2. Validates configured port and device type, confirming each with the client.
3. Checks device status and guides device activation via RAG if inactive.
4. Validates lu (last update) and since timestamps.
5. If lu <= 5 min (fresh), bypasses stale diagnostics and proceeds directly to fault classification.
6. If lu > 5 min (stale), runs command-based diagnosis:
   a. Asks user to run STATUS command and share screenshot -> analyze.
   b. If STATUS is clean, asks user to run PARAM command and share screenshot -> analyze.
   c. If PARAM is clean, proceeds to fault_classifier.
7. Only asks client to move vehicle when all configuration and diagnostic prerequisites are satisfied.
"""
from __future__ import annotations

from datetime import datetime
import logging
import re
from typing import Any

from trackobit_assistant.graph.state import AssistantState
from trackobit_assistant.schemas.models import ValidationStatus, VehicleSnapshot
from trackobit_assistant.services.device_command_map import (
    describe_status_command,
    get_param_command,
    get_status_command,
)
from trackobit_assistant.services.device_port_registry import (
    format_port_mismatch_message,
    get_expected_port,
    is_port_configured,
    is_port_matching,
)

logger = logging.getLogger("trackobit_assistant.nodes.check_config")


AFFIRMATIVE_PATTERN = re.compile(
    r"\b(y+[ea]+[sh]*|y+u+p+|y+e+p+|sure|ok(?:ay)?|correct|right|confirmed|true|fine|done|already\s+done|activated|renewed|haan?|theek|sahi|matches?)\b",
    re.IGNORECASE
)
NEGATIVE_PATTERN = re.compile(
    r"\b(no+|nah+|nope|not|wrong|incorrect|different|false|nahi|na|galat|doesn\'?t\s+match|don\'?t\s+match)\b",
    re.IGNORECASE
)
FIX_CONFIRM_PATTERN = re.compile(
    r"\b(done|fixed|updated|configured|changed|reconfigured|sent|already\s+done)\b",
    re.IGNORECASE
)


def _is_negative(text: str) -> bool:
    if not text:
        return False
    clean = str(text).strip().casefold()
    if re.search(r"\b(wrong|incorrect)\s+(distance|report|speed|location|reading|address|data|mileage|km|odometer|time|alert|route|playback)\b", clean):
        return False
    return bool(NEGATIVE_PATTERN.search(clean))


def _is_affirmative(text: str) -> bool:
    if not text:
        return False
    t = str(text).strip()
    if _is_negative(t):
        return False
    return bool(AFFIRMATIVE_PATTERN.search(t))


def _is_fix_confirmed(text: str) -> bool:
    if not text:
        return False
    if _is_negative(text):
        return False
    if _is_affirmative(text):
        return True
    return bool(FIX_CONFIRM_PATTERN.search(str(text).strip()))


def _get_rag_guidance(runtime: Any, query: str, default_text: str) -> str:
    kb = getattr(runtime, "knowledge_base", None)
    if kb:
        try:
            docs = kb.search(query, k=2)
            if docs and docs[0].get("content"):
                return docs[0]["content"].strip()
        except Exception as exc:
            logger.warning(f"[CHECK_CONFIG] Knowledge base search for '{query}' failed: {exc}")
    return default_text


def _refetch_snapshot(runtime: Any, vehicle_no: str, session_id: str) -> dict[str, Any] | None:
    """Re-fetch vehicle snapshot from API and return raw dict, or None on failure."""
    try:
        refreshed = runtime.vehicle_client.get_vehicle(vehicle_no)
        return refreshed.model_dump(mode="json")
    except Exception as exc:
        logger.warning(f"[CHECK_CONFIG] Could not re-fetch vehicle snapshot: {exc}", extra={"session_id": session_id})
        return None


def make_node(runtime: Any):
    def node(state: AssistantState) -> dict[str, Any]:
        session_id = state.get("session_id", "-")
        awaiting = state.get("awaiting", "none")
        user_message = state.get("last_user_message", "").strip()
        snapshot_dict = state.get("vehicle_snapshot") or {}
        vehicle_no = state.get("vehicle_no") or snapshot_dict.get("vehicle_no", "Unknown")

        logger.info(
            f"[CHECK_CONFIG] Start: awaiting='{awaiting}', vehicle='{vehicle_no}', diag_stage='{state.get('check_config_diag_stage')}'",
            extra={"session_id": session_id},
        )

        updates: dict[str, Any] = {"current_step": "check_config"}

        # ── Known bug early-exit ─────────────────────────────────────────────
        bug_store = getattr(runtime, "bug_store", None)
        if bug_store is not None and user_message:
            try:
                matched_bug = bug_store.search_active_bug(user_message, llm=runtime.llm, module=state.get("selected_module"))
                if matched_bug:
                    title = matched_bug.get("title")
                    bug_id = matched_bug.get("bug_id")
                    workaround = matched_bug.get("workaround") or "Our engineering team is actively resolving this."
                    eta = matched_bug.get("eta") or "in progress"
                    resp = (
                        f"⚠️ We have identified this as an active known issue: **{title}** (Reference: `{bug_id}`).\n\n"
                        f"• **Status**: Active (Fix ETA: {eta})\n"
                        f"• **Workaround**: {workaround}\n\n"
                        "Our engineering team is already working on resolving this issue."
                    )
                    return {
                        **updates,
                        "response": resp,
                        "awaiting": "none",
                        "resolved": True,
                        "fault_category": "known_software_outage",
                        "known_bug": matched_bug,
                        "current_step": "complete_frame",
                    }
            except Exception as e:
                logger.warning(f"[CHECK_CONFIG] Known bug search error: {e}")

        # ════════════════════════════════════════════════════════════════════
        # MULTI-TURN REPLY HANDLERS  (awaiting states)
        # ════════════════════════════════════════════════════════════════════

        # ── PRE-FLIGHT re-check: user configured missing IMEI ────────────────
        if awaiting == "config_imei_configure_confirm":
            if _is_fix_confirmed(user_message):
                new_snap = _refetch_snapshot(runtime, vehicle_no, session_id)
                if new_snap is None:
                    return {**updates, "current_step": "human_handoff", "handoff_reason": "vehicle_api_recheck_failed",
                            "response": "I couldn't verify the IMEI configuration due to an API error. Transferring you to support.", "awaiting": "none"}
                snapshot_dict = new_snap
                updates["vehicle_snapshot"] = snapshot_dict
                imei = str(snapshot_dict.get("imei") or "").strip()
                if imei:
                    updates["config_imei_status"] = ValidationStatus.VALID.value
                    state = {**state, "vehicle_snapshot": snapshot_dict, "config_imei_status": ValidationStatus.VALID.value, "awaiting": "none"}
                else:
                    return {**updates, "config_imei_status": ValidationStatus.INVALID.value, "current_step": "human_handoff",
                            "handoff_reason": "imei_still_missing_after_configure",
                            "response": f"The IMEI for vehicle {vehicle_no} is still not showing in the system after reconfiguration. Transferring you to support.", "awaiting": "none"}
            elif _is_negative(user_message):
                return {**updates, "config_imei_status": ValidationStatus.INVALID.value, "current_step": "human_handoff",
                        "handoff_reason": "imei_configuration_declined",
                        "response": f"I understand. Transferring you to our technical support team to configure the IMEI for vehicle {vehicle_no}.", "awaiting": "none"}
            else:
                return {**updates, "response": "Please let me know once you have configured the IMEI, or reply 'no' if you need assistance.", "awaiting": "config_imei_configure_confirm"}

        # ── PRE-FLIGHT re-check: user configured missing port ────────────────
        elif awaiting == "config_port_missing_confirm":
            if _is_fix_confirmed(user_message):
                new_snap = _refetch_snapshot(runtime, vehicle_no, session_id)
                if new_snap is None:
                    return {**updates, "current_step": "human_handoff", "handoff_reason": "vehicle_api_recheck_failed",
                            "response": "I couldn't verify the port configuration due to an API error. Transferring you to support.", "awaiting": "none"}
                snapshot_dict = new_snap
                updates["vehicle_snapshot"] = snapshot_dict
                port = snapshot_dict.get("port")
                if is_port_configured(port):
                    updates["config_port_status"] = ValidationStatus.VALID.value
                    state = {**state, "vehicle_snapshot": snapshot_dict, "config_port_status": ValidationStatus.VALID.value, "awaiting": "none"}
                else:
                    return {**updates, "config_port_status": ValidationStatus.INVALID.value, "current_step": "human_handoff",
                            "handoff_reason": "port_still_missing_after_configure",
                            "response": f"The port for vehicle {vehicle_no} is still not configured in the system. Transferring you to support.", "awaiting": "none"}
            elif _is_negative(user_message):
                return {**updates, "config_port_status": ValidationStatus.INVALID.value, "current_step": "human_handoff",
                        "handoff_reason": "port_configuration_declined",
                        "response": f"I understand. Transferring you to our technical support team to configure the communication port for vehicle {vehicle_no}.", "awaiting": "none"}
            else:
                return {**updates, "response": "Please let me know once you have configured the port, or reply 'no' if you need assistance.", "awaiting": "config_port_missing_confirm"}

        # ── PRE-FLIGHT re-check: user configured missing device type ─────────
        elif awaiting == "config_device_type_missing_confirm":
            if _is_fix_confirmed(user_message):
                new_snap = _refetch_snapshot(runtime, vehicle_no, session_id)
                if new_snap is None:
                    return {**updates, "current_step": "human_handoff", "handoff_reason": "vehicle_api_recheck_failed",
                            "response": "I couldn't verify the device type configuration due to an API error. Transferring you to support.", "awaiting": "none"}
                snapshot_dict = new_snap
                updates["vehicle_snapshot"] = snapshot_dict
                device_type = str(snapshot_dict.get("deviceType") or snapshot_dict.get("device_type") or "").strip()
                if device_type:
                    updates["config_device_type_status"] = ValidationStatus.VALID.value
                    state = {**state, "vehicle_snapshot": snapshot_dict, "config_device_type_status": ValidationStatus.VALID.value, "awaiting": "none"}
                else:
                    return {**updates, "config_device_type_status": ValidationStatus.INVALID.value, "current_step": "human_handoff",
                            "handoff_reason": "device_type_still_missing_after_configure",
                            "response": f"The device type for vehicle {vehicle_no} is still not configured in the system. Transferring you to support.", "awaiting": "none"}
            elif _is_negative(user_message):
                return {**updates, "config_device_type_status": ValidationStatus.INVALID.value, "current_step": "human_handoff",
                        "handoff_reason": "device_type_configuration_declined",
                        "response": f"I understand. Transferring you to our technical support team to configure the device type for vehicle {vehicle_no}.", "awaiting": "none"}
            else:
                return {**updates, "response": "Please let me know once you have configured the device type, or reply 'no' if you need assistance.", "awaiting": "config_device_type_missing_confirm"}

        # ── Existing awaiting: port confirmed by client ──────────────────────
        elif awaiting == "config_port_confirm":
            if _is_affirmative(user_message):
                logger.info("[CHECK_CONFIG] Port confirmed by client", extra={"session_id": session_id})
                updates["config_port_status"] = ValidationStatus.VALID.value
                state = {**state, "config_port_status": ValidationStatus.VALID.value, "awaiting": "none"}
            elif _is_negative(user_message):
                logger.warning("[CHECK_CONFIG] Port rejected by client", extra={"session_id": session_id})
                return {
                    **updates,
                    "config_port_status": ValidationStatus.INVALID.value,
                    "current_step": "human_handoff",
                    "handoff_reason": "incorrect_port_reconfiguration_required",
                    "response": (
                        f"Thank you for confirming. The configured port for vehicle {vehicle_no} "
                        "is incorrect. Automated remote reconfiguration is not available, so I am "
                        "transferring your case to our technical support team to update the port."
                    ),
                    "awaiting": "none",
                }
            else:
                port = snapshot_dict.get("port")
                return {**updates, "response": f"Please confirm with 'yes' or 'no': Is the device configured on port {port}?", "awaiting": "config_port_confirm"}

        # ── Existing awaiting: device type confirmed by client ───────────────
        elif awaiting == "config_device_type_confirm":
            if _is_affirmative(user_message):
                logger.info("[CHECK_CONFIG] Device type confirmed by client", extra={"session_id": session_id})
                updates["config_device_type_status"] = ValidationStatus.VALID.value
                state = {**state, "config_device_type_status": ValidationStatus.VALID.value, "awaiting": "none"}
            elif _is_negative(user_message):
                logger.warning("[CHECK_CONFIG] Device type rejected by client", extra={"session_id": session_id})
                return {
                    **updates,
                    "config_device_type_status": ValidationStatus.INVALID.value,
                    "current_step": "human_handoff",
                    "handoff_reason": "incorrect_device_type_reconfiguration_required",
                    "response": (
                        f"The registered device model for vehicle {vehicle_no} does not match your "
                        "installed physical hardware. Manual support assistance is required to update "
                        "device registration. Connecting you to support."
                    ),
                    "awaiting": "none",
                }
            else:
                dtype = snapshot_dict.get("device_type")
                return {**updates, "response": f"Please confirm with 'yes' or 'no': Is your installed device model '{dtype}'?", "awaiting": "config_device_type_confirm"}

        # ── Existing awaiting: port mismatch fix confirmed ───────────────────
        elif awaiting == "config_port_fix_confirm":
            if _is_fix_confirmed(user_message):
                logger.info("[CHECK_CONFIG] Client confirmed port was updated/reconfigured", extra={"session_id": session_id})
                new_snap = _refetch_snapshot(runtime, vehicle_no, session_id)
                if new_snap:
                    snapshot_dict = new_snap
                    updates["vehicle_snapshot"] = snapshot_dict
                updates["config_port_status"] = ValidationStatus.VALID.value
                state = {**state, "vehicle_snapshot": snapshot_dict, "config_port_status": ValidationStatus.VALID.value, "awaiting": "none"}
            elif _is_negative(user_message):
                logger.warning("[CHECK_CONFIG] Client unable to reconfigure port", extra={"session_id": session_id})
                return {
                    **updates,
                    "config_port_status": ValidationStatus.INVALID.value,
                    "current_step": "human_handoff",
                    "handoff_reason": "port_reconfiguration_assistance_required",
                    "response": (
                        f"I understand. I am transferring your request to our technical support team to assist with "
                        f"reconfiguring the communication port for vehicle {vehicle_no}."
                    ),
                    "awaiting": "none",
                }
            else:
                device_type = snapshot_dict.get("device_type")
                expected_port = get_expected_port(device_type) or "the required port"
                return {**updates, "response": f"Please let me know once you have updated the port to {expected_port}, or reply 'no' if you need technical support to assist you.", "awaiting": "config_port_fix_confirm"}

        # ── Existing awaiting: subscription renewal confirm ──────────────────
        elif awaiting == "subscription_renewal_confirm":
            logger.info("[CHECK_CONFIG] Client reports subscription renewal, re-fetching API...", extra={"session_id": session_id})
            new_snap = _refetch_snapshot(runtime, vehicle_no, session_id)
            if new_snap is None:
                return {**updates, "current_step": "human_handoff", "handoff_reason": "vehicle_api_recheck_failed",
                        "response": "I couldn't verify the renewed vehicle subscription due to an API error. Transferring you to support.", "awaiting": "none"}
            snapshot_dict = new_snap
            updates["vehicle_snapshot"] = snapshot_dict
            v_status = snapshot_dict.get("vehicle_status") or ""
            if v_status.casefold() == "active":
                logger.info("[CHECK_CONFIG] Vehicle verified active after renewal", extra={"session_id": session_id})
                updates["subscription_status"] = ValidationStatus.VALID.value
                state = {**state, "vehicle_snapshot": snapshot_dict, "subscription_status": ValidationStatus.VALID.value, "awaiting": "none"}
            else:
                logger.warning("[CHECK_CONFIG] Vehicle still inactive after renewal attempt", extra={"session_id": session_id})
                return {
                    **updates,
                    "subscription_status": ValidationStatus.INVALID.value,
                    "current_step": "human_handoff",
                    "handoff_reason": "vehicle_inactive_after_renewal_attempt",
                    "response": (
                        f"I re-checked vehicle {vehicle_no}, but the status is still showing Inactive. "
                        "Connecting you to support to verify the subscription."
                    ),
                    "awaiting": "none",
                }

        # ── Existing awaiting: device activation confirm ─────────────────────
        elif awaiting == "device_activation_confirm":
            logger.info("[CHECK_CONFIG] Client reports device activation, re-fetching API...", extra={"session_id": session_id})
            new_snap = _refetch_snapshot(runtime, vehicle_no, session_id)
            if new_snap is None:
                return {**updates, "current_step": "human_handoff", "handoff_reason": "device_api_recheck_failed",
                        "response": "I couldn't verify the device status due to an API error. Transferring you to support.", "awaiting": "none"}
            snapshot_dict = new_snap
            updates["vehicle_snapshot"] = snapshot_dict
            d_status = snapshot_dict.get("device_status") or ""
            if d_status.casefold() == "active":
                logger.info("[CHECK_CONFIG] Device verified active after activation", extra={"session_id": session_id})
                updates["device_activation_status"] = ValidationStatus.VALID.value
                state = {**state, "vehicle_snapshot": snapshot_dict, "device_activation_status": ValidationStatus.VALID.value, "awaiting": "none"}
            else:
                logger.warning("[CHECK_CONFIG] Device still inactive after activation attempt", extra={"session_id": session_id})
                return {
                    **updates,
                    "device_activation_status": ValidationStatus.INVALID.value,
                    "current_step": "human_handoff",
                    "handoff_reason": "device_activation_failed",
                    "response": (
                        f"I checked the system records, but the device for vehicle {vehicle_no} is still showing Inactive. "
                        "Transferring you to our support team to investigate."
                    ),
                    "awaiting": "none",
                }

        # ── Existing awaiting: move vehicle confirm ──────────────────────────
        elif awaiting == "config_move_vehicle":
            if _is_affirmative(user_message):
                logger.info("[CHECK_CONFIG] Client confirmed vehicle location updated after move", extra={"session_id": session_id})
                return {**updates, "current_step": "fault_classifier", "response": "The vehicle location is updating properly.", "awaiting": "none", "config_step": "completed"}
            elif _is_negative(user_message):
                logger.warning("[CHECK_CONFIG] Location still not updating after vehicle move", extra={"session_id": session_id})
                return {
                    **updates,
                    "current_step": "human_handoff",
                    "handoff_reason": "location_unresolved_after_vehicle_movement",
                    "response": (
                        f"Vehicle {vehicle_no} is still not updating its location after movement. "
                        "I am escalating this ticket with all collected configuration and diagnostic details to technical support."
                    ),
                    "awaiting": "none",
                }
            else:
                return {**updates, "response": "Did the vehicle's location update on your dashboard after moving it? Please reply with 'yes' or 'no'.", "awaiting": "config_move_vehicle"}

        # ════════════════════════════════════════════════════════════════════
        # SEQUENTIAL VALIDATION
        # ════════════════════════════════════════════════════════════════════

        # Pull fresh raw fields (API uses camelCase, VehicleSnapshot uses snake_case)
        raw = snapshot_dict.get("raw_payload", {}).get("data", snapshot_dict)
        port = snapshot_dict.get("port") or raw.get("port")
        device_type = (
            snapshot_dict.get("device_type")
            or raw.get("deviceType")
            or ""
        )
        device_type = str(device_type).strip()
        imei = str(snapshot_dict.get("imei") or raw.get("imei") or "").strip()
        lu_raw = snapshot_dict.get("lu") or raw.get("lu") or ""
        sub_due = snapshot_dict.get("subscription_due") or raw.get("subscriptionDue") or ""
        sub_start = raw.get("subscriptionStart") or ""

        # ── PRE-FLIGHT 1: lu must not be empty ───────────────────────────────
        if not str(lu_raw).strip():
            logger.warning("[CHECK_CONFIG] 'lu' (last update) field is empty in API response", extra={"session_id": session_id})
            return {
                **updates,
                "lu_status": ValidationStatus.UNKNOWN.value,
                "current_step": "human_handoff",
                "handoff_reason": "lu_field_missing_in_api",
                "response": (
                    f"We're unable to determine the last update time for vehicle {vehicle_no} "
                    "as the field is missing in system records. Transferring you to support."
                ),
                "awaiting": "none",
            }

        # ── PRE-FLIGHT 2: subscriptionDue must not be empty ──────────────────
        if not str(sub_due).strip():
            logger.warning("[CHECK_CONFIG] 'subscriptionDue' field is empty", extra={"session_id": session_id})
            return {
                **updates,
                "current_step": "human_handoff",
                "handoff_reason": "subscription_due_field_missing",
                "response": (
                    f"The subscription due date for vehicle {vehicle_no} is not recorded in the system. "
                    "Transferring you to support to verify the account."
                ),
                "awaiting": "none",
            }

        # ── PRE-FLIGHT 3: subscriptionStart must not be empty ────────────────
        if not str(sub_start).strip():
            logger.warning("[CHECK_CONFIG] 'subscriptionStart' field is empty", extra={"session_id": session_id})
            return {
                **updates,
                "current_step": "human_handoff",
                "handoff_reason": "subscription_start_field_missing",
                "response": (
                    f"The subscription start date for vehicle {vehicle_no} is not recorded in the system. "
                    "Transferring you to support to verify the account."
                ),
                "awaiting": "none",
            }

        # ── PRE-FLIGHT 4: deviceType must not be empty ───────────────────────
        if not device_type:
            logger.warning("[CHECK_CONFIG] 'deviceType' is missing", extra={"session_id": session_id})
            return {
                **updates,
                "config_device_type_status": ValidationStatus.INVALID.value,
                "response": (
                    f"The device type (tracker model) for vehicle {vehicle_no} is not configured in the system. "
                    "Please configure the correct device model in your TrackoBit dashboard under Vehicle/Device Management, "
                    "then let me know once it's done."
                ),
                "awaiting": "config_device_type_missing_confirm",
                "current_step": "check_config",
            }

        # ── PRE-FLIGHT 5: vehicleStatus must be Active ───────────────────────
        vehicle_status = str(snapshot_dict.get("vehicle_status") or raw.get("vehicleStatus") or "").strip()
        if vehicle_status.casefold() != "active":
            is_expired = False
            if sub_due:
                try:
                    if isinstance(sub_due, str):
                        # Handle dd/MM/yyyy format from API
                        try:
                            due_dt = datetime.strptime(sub_due.strip(), "%d/%m/%Y")
                        except ValueError:
                            due_dt = datetime.fromisoformat(sub_due.replace("Z", "+00:00"))
                        is_expired = due_dt.date() < datetime.now().date()
                    elif isinstance(sub_due, datetime):
                        is_expired = sub_due.date() < datetime.now().date()
                except (ValueError, TypeError):
                    is_expired = False

            if is_expired:
                guidance = _get_rag_guidance(
                    runtime,
                    "subscription renewal",
                    "To renew: Navigate to Billing & Subscriptions in your TrackoBit portal, select the vehicle, and complete renewal payment.",
                )
                return {
                    **updates,
                    "subscription_status": ValidationStatus.INVALID.value,
                    "response": (
                        f"⚠️ The subscription for vehicle **{vehicle_no}** has expired "
                        f"(due date: {sub_due}).\n\n"
                        f"{guidance}\n\n"
                        "Please renew your subscription and let me know once it's done."
                    ),
                    "awaiting": "subscription_renewal_confirm",
                    "current_step": "check_config",
                }
            else:
                logger.warning("[CHECK_CONFIG] Vehicle inactive with unexpired or unknown subscription", extra={"session_id": session_id})
                return {
                    **updates,
                    "subscription_status": ValidationStatus.UNKNOWN.value,
                    "current_step": "human_handoff",
                    "handoff_reason": "vehicle_inactive_unexplained",
                    "response": (
                        f"Vehicle {vehicle_no} is marked Inactive in the system, but the subscription does not appear to be expired. "
                        "Transferring you to our support team to verify the account status."
                    ),
                    "awaiting": "none",
                }

        # ── PRE-FLIGHT 6: imei must not be empty ─────────────────────────────
        if state.get("config_imei_status") != ValidationStatus.VALID.value:
            if not imei:
                logger.warning("[CHECK_CONFIG] 'imei' is missing", extra={"session_id": session_id})
                return {
                    **updates,
                    "config_imei_status": ValidationStatus.INVALID.value,
                    "response": (
                        f"The IMEI number for vehicle {vehicle_no} is not configured in the system. "
                        "Please update the IMEI in your TrackoBit dashboard under Vehicle/Device Management, "
                        "then let me know once it's done."
                    ),
                    "awaiting": "config_imei_configure_confirm",
                    "current_step": "check_config",
                }
            updates["config_imei_status"] = ValidationStatus.VALID.value

        # ── PRE-FLIGHT 7: port must not be empty ─────────────────────────────
        if state.get("config_port_status") != ValidationStatus.VALID.value:
            if not is_port_configured(port):
                logger.warning("[CHECK_CONFIG] 'port' is missing or zero", extra={"session_id": session_id})
                device_type_label = device_type or "your tracker"
                expected_port = get_expected_port(device_type)
                port_hint = f" ({device_type_label} typically uses port {expected_port})" if expected_port else ""
                return {
                    **updates,
                    "config_port_status": ValidationStatus.INVALID.value,
                    "response": (
                        f"The communication port for vehicle {vehicle_no} is not configured in the system{port_hint}. "
                        "Please configure the correct port in your TrackoBit dashboard, then let me know once it's done."
                    ),
                    "awaiting": "config_port_missing_confirm",
                    "current_step": "check_config",
                }

        # ════════════════════════════════════════════════════════════════════
        # EXISTING CHECKS: Device type & port confirmation (when unreachable)
        # ════════════════════════════════════════════════════════════════════
        device_state = str(snapshot_dict.get("state") or snapshot_dict.get("vehicle_status") or "").strip().lower()
        raw_minutes = snapshot_dict.get("minutes_since_last_update")
        try:
            minutes_float = float(raw_minutes) if raw_minutes is not None else None
        except (ValueError, TypeError):
            minutes_float = None

        is_unreachable = (device_state == "unreachable")
        is_stale_over_10m = (minutes_float is not None and minutes_float > 10.0)

        should_validate_device_type = is_unreachable
        should_validate_port = is_unreachable and is_stale_over_10m

        if should_validate_device_type:
            device_type_status = state.get("config_device_type_status")
            if device_type_status != ValidationStatus.VALID.value:
                return {
                    **updates,
                    "response": f"The device model registered in our system is '{device_type}'. Does this match your installed physical device?",
                    "awaiting": "config_device_type_confirm",
                    "current_step": "check_config",
                }
        else:
            updates["config_device_type_status"] = ValidationStatus.VALID.value

        if should_validate_port:
            port_status = state.get("config_port_status")
            if port_status != ValidationStatus.VALID.value:
                expected_port = get_expected_port(device_type)
                if expected_port and str(port).strip() != str(expected_port).strip():
                    msg = format_port_mismatch_message(
                        vehicle_no=vehicle_no,
                        device_type=device_type,
                        actual_port=port,
                        expected_port=expected_port,
                        command_registry=getattr(runtime, "command_registry", None),
                    )
                    return {**updates, "config_port_status": ValidationStatus.INVALID.value, "response": msg,
                            "awaiting": "config_port_fix_confirm", "current_step": "check_config"}
                else:
                    return {**updates,
                            "response": f"The device is configured on port {port}. Can you please confirm if this matches the port your device is sending data to?",
                            "awaiting": "config_port_confirm", "current_step": "check_config"}
        else:
            updates["config_port_status"] = ValidationStatus.VALID.value

        # ── Device Status ─────────────────────────────────────────────────────
        device_status = str(snapshot_dict.get("device_status") or "").strip()
        if device_status.casefold() != "active":
            guidance = _get_rag_guidance(
                runtime,
                "device activation",
                "To activate: Open Vehicle/Device Management in TrackoBit, locate the vehicle, and toggle Device Status to Active.",
            )
            return {
                **updates,
                "device_activation_status": ValidationStatus.INVALID.value,
                "response": (
                    f"The device associated with vehicle {vehicle_no} is currently Inactive.\n\n"
                    f"{guidance}\n\n"
                    "Please let me know once you have activated the device."
                ),
                "awaiting": "device_activation_confirm",
                "current_step": "check_config",
            }

        # ── Overspeed State Check ─────────────────────────────────────────────
        state_str = str(snapshot_dict.get("state") or "").strip().lower()
        if "overspeed" in state_str:
            speeding_threshold = (
                snapshot_dict.get("speeding_threshold")
                or snapshot_dict.get("speedingThreshold")
                or snapshot_dict.get("speed_threshold")
                or snapshot_dict.get("speedThreshold")
                or snapshot_dict.get("overspeed_threshold")
                or snapshot_dict.get("overspeedThreshold")
                or snapshot_dict.get("speedLimit")
                or snapshot_dict.get("speed_limit")
                or raw.get("speedingThreshold")
                or raw.get("speeding_threshold")
                or raw.get("speedThreshold")
                or raw.get("speed_threshold")
                or raw.get("overspeedThreshold")
                or raw.get("overspeed_threshold")
                or raw.get("speedLimit")
                or raw.get("speed_limit")
                or snapshot_dict.get("raw_payload", {}).get("data", {}).get("terminalPacketMeta", {}).get("speedingThreshold")
                or snapshot_dict.get("raw_payload", {}).get("data", {}).get("terminalPacketMeta", {}).get("speeding_threshold")
            )
            try:
                thresh_val = float(speeding_threshold) if speeding_threshold is not None else None
            except (ValueError, TypeError):
                thresh_val = None

            if thresh_val is None or thresh_val <= 0:
                logger.warning("[CHECK_CONFIG] State is overspeeding but speeding threshold is not configured in API", extra={"session_id": session_id})
                return {
                    **updates,
                    "speeding_threshold_status": ValidationStatus.INVALID.value,
                    "current_step": "human_handoff",
                    "handoff_reason": "missing_speeding_threshold",
                    "response": (
                        f"Vehicle {vehicle_no} is currently showing status 'Overspeeding', but no speeding threshold "
                        "is configured in system records. Transferring you to support to check the speed limit settings."
                    ),
                    "awaiting": "none",
                }

            current_speed = (
                snapshot_dict.get("speed")
                or raw.get("speed")
                or snapshot_dict.get("raw_payload", {}).get("data", {}).get("terminalPacketMeta", {}).get("speed")
            )
            try:
                speed_val = float(current_speed) if current_speed is not None else None
            except (ValueError, TypeError):
                speed_val = None

            updates["speeding_threshold"] = thresh_val
            updates["speed"] = speed_val

            if speed_val is not None and speed_val <= thresh_val:
                logger.warning(f"[CHECK_CONFIG] State is overspeeding but speed ({speed_val}) does not exceed threshold ({thresh_val})", extra={"session_id": session_id})
                return {
                    **updates,
                    "speeding_threshold_status": ValidationStatus.INVALID.value,
                    "current_step": "human_handoff",
                    "handoff_reason": "overspeeding_state_below_threshold",
                    "response": (
                        f"Vehicle {vehicle_no} is marked as 'Overspeeding', but its recorded speed ({speed_val} km/h) "
                        f"is within the configured speeding threshold ({thresh_val} km/h). "
                        "Transferring you to technical support to investigate this alerting anomaly."
                    ),
                    "awaiting": "none",
                }

            logger.info(f"[CHECK_CONFIG] Overspeeding state verified: threshold={thresh_val} km/h, speed={speed_val} km/h", extra={"session_id": session_id})
            updates["speeding_threshold_status"] = ValidationStatus.VALID.value

        # ── lu / since Validation ─────────────────────────────────────────────
        minutes = snapshot_dict.get("minutes_since_last_update")
        try:
            minutes = float(minutes) if minutes is not None else None
        except (ValueError, TypeError):
            minutes = None

        if minutes is None:
            logger.warning("[CHECK_CONFIG] minutes_since_last_update is missing or invalid", extra={"session_id": session_id})
            return {
                **updates,
                "lu_status": ValidationStatus.UNKNOWN.value,
                "current_step": "human_handoff",
                "handoff_reason": "lu_timestamp_uninterpretable",
                "response": "The last-update timestamp for this vehicle cannot be interpreted. Connecting you to support.",
                "awaiting": "none",
            }

        hours_since = snapshot_dict.get("hours_since_status")
        updates["since_status"] = ValidationStatus.INVALID.value if (hours_since is not None and hours_since > 24.0) else ValidationStatus.VALID.value

        # ── lu <= 5 min: fresh → proceed to fault_classifier ─────────────────
        if minutes <= 5.0:
            logger.info(f"[CHECK_CONFIG] lu is fresh ({minutes:.1f} mins) → fault_classifier", extra={"session_id": session_id})
            return {
                **updates,
                "lu_status": ValidationStatus.VALID.value,
                "current_step": "fault_classifier",
                "awaiting": "none",
                "config_step": "completed",
                "check_config_diag_stage": None,
            }

        # ════════════════════════════════════════════════════════════════════
        # lu > 5 min: COMMAND-BASED STALE DIAGNOSIS
        # ════════════════════════════════════════════════════════════════════
        logger.info(f"[CHECK_CONFIG] lu is stale ({minutes:.1f} mins) → command-based diagnosis", extra={"session_id": session_id})
        updates["lu_status"] = ValidationStatus.INVALID.value

        command_registry = getattr(runtime, "command_registry", None)
        diag_stage = state.get("check_config_diag_stage") or "status"

        if diag_stage in ("status", None, ""):
            # ── Step A: STATUS command ────────────────────────────────────────
            if not device_type:
                # Should have been caught in pre-flight but guard here too
                return {
                    **updates,
                    "response": (
                        f"The device type for vehicle {vehicle_no} is not configured — I need it to look up the diagnostic command. "
                        "Please configure the device model and let me know once done."
                    ),
                    "awaiting": "config_device_type_missing_confirm",
                    "current_step": "check_config",
                    "check_config_diag_stage": "status",
                }

            status_cmd = get_status_command(device_type, command_registry) if command_registry else None
            instruction = describe_status_command(status_cmd, device_type)

            logger.info(
                f"[CHECK_CONFIG] Presenting STATUS command for device_type='{device_type}': '{status_cmd.command if status_cmd else 'N/A'}'",
                extra={"session_id": session_id},
            )
            return {
                **updates,
                "check_config_diag_stage": "status",
                "current_command": status_cmd.model_dump(mode="json") if status_cmd else None,
                "lu_status": ValidationStatus.INVALID.value,
                "response": (
                    f"The vehicle's last data update was **{minutes:.0f} minutes ago**, which indicates the device may not be communicating with the server.\n\n"
                    f"To diagnose this, please run the **STATUS command**:\n\n"
                    f"{instruction}\n\n"
                    "Once you have the reply, share a clear screenshot and I'll analyse it."
                ),
                "awaiting": "command_screenshot",
                "current_step": "check_config",
            }

        elif diag_stage == "param":
            # ── Step B: PARAM command ─────────────────────────────────────────
            param_cmd = get_param_command(device_type, command_registry) if command_registry else None

            if param_cmd is None:
                logger.warning(f"[CHECK_CONFIG] No PARAM command found for '{device_type}'; proceeding to fault_classifier", extra={"session_id": session_id})
                return {
                    **updates,
                    "check_config_diag_stage": None,
                    "current_step": "fault_classifier",
                    "awaiting": "none",
                    "config_step": "completed",
                    "response": "",
                }

            logger.info(
                f"[CHECK_CONFIG] Presenting PARAM command for device_type='{device_type}': '{param_cmd.command}'",
                extra={"session_id": session_id},
            )
            return {
                **updates,
                "check_config_diag_stage": "param",
                "current_command": param_cmd.model_dump(mode="json"),
                "response": (
                    "The STATUS check looks fine. Now let's verify the device's server and IMEI configuration.\n\n"
                    f"Please run the **PARAM command**:\n\n"
                    f"Send `{param_cmd.command}` to the device via SMS or the TrackoBit command terminal, "
                    "and share a clear screenshot of the full reply."
                ),
                "awaiting": "command_screenshot",
                "current_step": "check_config",
            }

        # Fallback safety net
        logger.warning(f"[CHECK_CONFIG] Unexpected diag_stage='{diag_stage}'; routing to fault_classifier", extra={"session_id": session_id})
        return {
            **updates,
            "check_config_diag_stage": None,
            "current_step": "fault_classifier",
            "awaiting": "none",
            "config_step": "completed",
        }

    return node
