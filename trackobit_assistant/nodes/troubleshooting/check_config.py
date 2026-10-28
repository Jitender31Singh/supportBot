"""Check configuration node for vehicle and device validation before fault classification.

Follows support procedures:
1. Validates configured port and device type, confirming each with the client.
2. Checks vehicle status and subscription expiry (vehicle takes precedence).
3. Checks device status and guides device activation via RAG if inactive.
4. Validates lu (last update) and since timestamps.
5. If lu <= 5 min (fresh), bypasses stale diagnostics and proceeds directly to fault classification.
6. If lu > 5 min (stale), invokes modular diagnostic stubs (check_ip, check_port, check_imei).
   If diagnostics are unavailable, safely escalates with diagnostic context.
7. Only asks client to move vehicle when all configuration and diagnostic prerequisites are satisfied.
"""
from __future__ import annotations

from datetime import datetime
import logging
import re
from typing import Any

from trackobit_assistant.graph.state import AssistantState
from trackobit_assistant.schemas.models import ValidationStatus, VehicleSnapshot
from trackobit_assistant.services.device_diagnostics import check_imei, check_ip, check_port
from trackobit_assistant.services.device_port_registry import (
    format_port_mismatch_message,
    get_device_port_info,
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
    # Guard against customer symptom phrasing that uses "wrong" or "incorrect" to describe telemetry or reports
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


def make_node(runtime: Any):
    def node(state: AssistantState) -> dict[str, Any]:
        session_id = state.get("session_id", "-")
        awaiting = state.get("awaiting", "none")
        user_message = state.get("last_user_message", "").strip()
        snapshot_dict = state.get("vehicle_snapshot") or {}
        vehicle_no = state.get("vehicle_no") or snapshot_dict.get("vehicle_no", "Unknown")

        logger.info(
            f"[CHECK_CONFIG] Start check_config: awaiting='{awaiting}', vehicle='{vehicle_no}'",
            extra={"session_id": session_id},
        )

        updates: dict[str, Any] = {"current_step": "check_config"}

        # Check if user message matches an active known bug early
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

        # -----------------------------------------------------------------
        # Multi-turn reply handling based on awaiting state
        # -----------------------------------------------------------------
        if awaiting == "config_port_confirm":
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
                return {
                    **updates,
                    "response": f"Please confirm with 'yes' or 'no': Is the device configured on port {port}?",
                    "awaiting": "config_port_confirm",
                }

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
                return {
                    **updates,
                    "response": f"Please confirm with 'yes' or 'no': Is your installed device model '{dtype}'?",
                    "awaiting": "config_device_type_confirm",
                }

        elif awaiting == "config_port_fix_confirm":
            if _is_fix_confirmed(user_message):
                logger.info("[CHECK_CONFIG] Client confirmed port was updated/reconfigured", extra={"session_id": session_id})
                try:
                    refreshed = runtime.vehicle_client.get_vehicle(vehicle_no)
                    snapshot_dict = refreshed.model_dump(mode="json")
                    updates["vehicle_snapshot"] = snapshot_dict
                except Exception as exc:
                    logger.warning(f"[CHECK_CONFIG] Could not re-fetch vehicle snapshot: {exc}", extra={"session_id": session_id})
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
                return {
                    **updates,
                    "response": f"Please let me know once you have updated the port to {expected_port}, or reply 'no' if you need technical support to assist you.",
                    "awaiting": "config_port_fix_confirm",
                }

        elif awaiting == "subscription_renewal_confirm":
            logger.info("[CHECK_CONFIG] Client reports subscription renewal, re-fetching API...", extra={"session_id": session_id})
            try:
                refreshed = runtime.vehicle_client.get_vehicle(vehicle_no)
                snapshot_dict = refreshed.model_dump(mode="json")
                updates["vehicle_snapshot"] = snapshot_dict
            except Exception as exc:
                logger.error(f"[CHECK_CONFIG] Failed to re-fetch vehicle snapshot: {exc}", extra={"session_id": session_id})
                return {
                    **updates,
                    "current_step": "human_handoff",
                    "handoff_reason": "vehicle_api_recheck_failed",
                    "response": "I couldn't verify the renewed vehicle subscription due to an API error. Transferring you to support.",
                    "awaiting": "none",
                }

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

        elif awaiting == "device_activation_confirm":
            logger.info("[CHECK_CONFIG] Client reports device activation, re-fetching API...", extra={"session_id": session_id})
            try:
                refreshed = runtime.vehicle_client.get_vehicle(vehicle_no)
                snapshot_dict = refreshed.model_dump(mode="json")
                updates["vehicle_snapshot"] = snapshot_dict
            except Exception as exc:
                logger.error(f"[CHECK_CONFIG] Failed to re-fetch device status: {exc}", extra={"session_id": session_id})
                return {
                    **updates,
                    "current_step": "human_handoff",
                    "handoff_reason": "device_api_recheck_failed",
                    "response": "I couldn't verify the device status due to an API error. Transferring you to support.",
                    "awaiting": "none",
                }

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

        elif awaiting == "config_move_vehicle":
            if _is_affirmative(user_message):
                logger.info("[CHECK_CONFIG] Client confirmed vehicle location updated after move", extra={"session_id": session_id})
                return {
                    **updates,
                    "current_step": "fault_classifier",
                    "response": "The vehicle location is updating properly.",
                    "awaiting": "none",
                    "config_step": "completed",
                }
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
                return {
                    **updates,
                    "response": "Did the vehicle's location update on your dashboard after moving it? Please reply with 'yes' or 'no'.",
                    "awaiting": "config_move_vehicle",
                }

        # -----------------------------------------------------------------
        # Sequential Configuration & Status Validation
        # -----------------------------------------------------------------
        port = snapshot_dict.get("port")
        device_type = snapshot_dict.get("device_type")

        # 1. Port & Device Type checks
        # Rules:
        # - If status is unreachable and lu > 10m: validate BOTH device type and port (with mismatch guidance).
        # - If status is unreachable but lu <= 10m: acknowledge / validate device type ONLY (bypass port check).
        # - If status is not unreachable: bypass both.
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
            if not device_type or str(device_type).strip() == "":
                logger.warning("[CHECK_CONFIG] Device type is missing", extra={"session_id": session_id})
                return {
                    **updates,
                    "config_device_type_status": ValidationStatus.INVALID.value,
                    "current_step": "human_handoff",
                    "handoff_reason": "missing_device_type",
                    "response": (
                        f"The device model for vehicle {vehicle_no} is missing in system records. "
                        "Transferring you to support."
                    ),
                    "awaiting": "none",
                }

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
            if not is_port_configured(port):
                logger.warning("[CHECK_CONFIG] Configured port is not configured (missing, empty, or 0)", extra={"session_id": session_id})
                expected_port = get_expected_port(device_type)
                port_hint = f" ({device_type} requires port {expected_port})" if expected_port and is_port_configured(expected_port) else ""
                return {
                    **updates,
                    "config_port_status": ValidationStatus.INVALID.value,
                    "current_step": "human_handoff",
                    "handoff_reason": "missing_configured_port",
                    "response": (
                        f"The communication port for vehicle {vehicle_no} is not configured in system records{port_hint}. "
                        "Transferring you to support to configure the port."
                    ),
                    "awaiting": "none",
                }

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
                    return {
                        **updates,
                        "config_port_status": ValidationStatus.INVALID.value,
                        "response": msg,
                        "awaiting": "config_port_fix_confirm",
                        "current_step": "check_config",
                    }
                else:
                    return {
                        **updates,
                        "response": f"The device is configured on port {port}. Can you please confirm if this matches the port your device is sending data to?",
                        "awaiting": "config_port_confirm",
                        "current_step": "check_config",
                    }
        else:
            updates["config_port_status"] = ValidationStatus.VALID.value

        # 2. Precedence: Vehicle Status & Subscription Check
        vehicle_status = str(snapshot_dict.get("vehicle_status") or "").strip()
        if vehicle_status.casefold() != "active":
            due = snapshot_dict.get("subscription_due")
            is_expired = False
            if due:
                if isinstance(due, str):
                    try:
                        due_dt = datetime.fromisoformat(due)
                        is_expired = due_dt.date() < datetime.now().date()
                    except ValueError:
                        is_expired = False
                elif isinstance(due, datetime):
                    is_expired = due.date() < datetime.now().date()

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
                        f"The subscription for vehicle {vehicle_no} has expired.\n\n"
                        f"{guidance}\n\n"
                        "Please let me know once you have completed the renewal."
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
                        f"Vehicle {vehicle_no} is marked Inactive in the system, but the subscription is not expired. "
                        "Transferring you to our support team to verify the account status."
                    ),
                    "awaiting": "none",
                }

        # 3. Device Status Check
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

        # 4. lu & since Validation
        minutes = snapshot_dict.get("minutes_since_last_update")
        try:
            minutes = float(minutes) if minutes is not None else None
        except (ValueError, TypeError):
            minutes = None

        if minutes is None:
            logger.warning("[CHECK_CONFIG] lu is missing or invalid", extra={"session_id": session_id})
            return {
                **updates,
                "lu_status": ValidationStatus.UNKNOWN.value,
                "current_step": "human_handoff",
                "handoff_reason": "lu_timestamp_uninterpretable",
                "response": "The last-update timestamp for this vehicle cannot be interpreted. Connecting you to support.",
                "awaiting": "none",
            }

        hours_since = snapshot_dict.get("hours_since_status")
        if hours_since is not None and hours_since > 24.0:
            updates["since_status"] = ValidationStatus.INVALID.value
        else:
            updates["since_status"] = ValidationStatus.VALID.value

        # Fresh update (lu <= 5 minutes): bypass stale diagnostics and movement
        if minutes <= 5.0:
            logger.info(f"[CHECK_CONFIG] lu is fresh ({minutes:.1f} mins). Routing to fault_classifier", extra={"session_id": session_id})
            updates["lu_status"] = ValidationStatus.VALID.value
            return {
                **updates,
                "current_step": "fault_classifier",
                "awaiting": "none",
                "config_step": "completed",
            }

        # Stale update (lu > 5 minutes): run modular diagnostics
        logger.info(f"[CHECK_CONFIG] lu is stale ({minutes:.1f} mins). Running packet diagnostics...", extra={"session_id": session_id})
        updates["lu_status"] = ValidationStatus.INVALID.value

        snapshot_obj = VehicleSnapshot(**snapshot_dict)
        diag_ip = check_ip(snapshot_obj)
        diag_port = check_port(snapshot_obj)
        diag_imei = check_imei(snapshot_obj)

        diagnostics_map = {
            "check_ip": diag_ip.model_dump(mode="json"),
            "check_port": diag_port.model_dump(mode="json"),
            "check_imei": diag_imei.model_dump(mode="json"),
        }
        updates["stale_diagnostics"] = diagnostics_map

        # Check if all required diagnostics are VALID
        all_valid = all(d.status == ValidationStatus.VALID for d in [diag_ip, diag_port, diag_imei])
        if not all_valid:
            logger.warning("[CHECK_CONFIG] Stale diagnostics are unavailable or unverified; escalating safely", extra={"session_id": session_id})
            return {
                **updates,
                "current_step": "human_handoff",
                "handoff_reason": "stale_packets_diagnostics_unavailable",
                "response": (
                    f"The vehicle's last update was {minutes:.1f} minutes ago. "
                    "Diagnostic packet checks (IP, port, and gateway logs) are currently unavailable in the automated system. "
                    "I am transferring your request to our technical support team with all collected configuration and telemetry data."
                ),
                "awaiting": "none",
            }

        # If all diagnostics were valid (future implementation), ask client to move vehicle
        return {
            **updates,
            "response": (
                "Configuration and diagnostic checks have passed. Please take the vehicle for a short 2-3 minute "
                "drive with ignition ON, and let me know if the live location updates on your dashboard."
            ),
            "awaiting": "config_move_vehicle",
            "current_step": "check_config",
        }

    return node
