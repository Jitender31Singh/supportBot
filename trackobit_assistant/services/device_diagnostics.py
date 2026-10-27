"""Device diagnostic extension points for validating IP, port, and IMEI packet delivery.

These methods provide typed, modular diagnostic check results. When the underlying
diagnostic tools or network probes are not implemented or available, they return
ValidationStatus.UNAVAILABLE without fabricating verification.
"""
from __future__ import annotations

from typing import Any
from trackobit_assistant.schemas.models import DiagnosticCheckResult, ValidationStatus, VehicleSnapshot


def check_ip(snapshot: VehicleSnapshot) -> DiagnosticCheckResult:
    """Check IP connectivity and packet delivery for the device."""
    return DiagnosticCheckResult(
        check_name="check_ip",
        status=ValidationStatus.UNAVAILABLE,
        evidence=["Remote server IP listener check not implemented in current runtime environment."],
        details={"ip_check_supported": False},
        recommended_action="Escalate to human support for server socket verification.",
    )


def check_port(snapshot: VehicleSnapshot) -> DiagnosticCheckResult:
    """Check whether server port is open and listening for device packets."""
    port = snapshot.port
    return DiagnosticCheckResult(
        check_name="check_port",
        status=ValidationStatus.UNAVAILABLE,
        evidence=[f"Port listener diagnostic for port '{port}' not implemented in current runtime."],
        details={"port": port, "port_check_supported": False},
        recommended_action="Escalate to human support for port gateway verification.",
    )


def check_imei(snapshot: VehicleSnapshot) -> DiagnosticCheckResult:
    """Check whether device IMEI is sending valid raw packets to the gateway."""
    imei = snapshot.imei
    return DiagnosticCheckResult(
        check_name="check_imei",
        status=ValidationStatus.UNAVAILABLE,
        evidence=[f"Gateway packet log trace for IMEI '{imei}' not implemented in current runtime."],
        details={"imei": imei, "imei_check_supported": False},
        recommended_action="Escalate to human support for gateway raw packet inspection.",
    )
