import re
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo
from trackobit_assistant.schemas.models import VehicleSnapshot

# Comprehensive Indian vehicle registration number search pattern
# Standard: State (2 letters) + District (1-2 digits) + optional series/category (0-4 letters) + Number (4 digits)
# BH series: Year (2 digits) + BH + Number (4 digits) + series (1-2 letters)
VEHICLE_NO_SEARCH_PATTERN = re.compile(
    r'(?i)\b(?:'
    r'[A-Z]{2}\s*[- ]?\d{1,2}(?:\s*[- ]?[A-Z]+)*\s*[- ]?\d{4}'
    r'|'
    r'\d{2}\s*[- ]?BH\s*[- ]?\d{4}\s*[- ]?[A-Z]{1,2}'
    r')\b'
)

VEHICLE_NO_NORMALIZED_PATTERN = re.compile(
    r'^(?:[A-Z]{2}\d{1,2}[A-Z]{0,4}\d{4}|\d{2}BH\d{4}[A-Z]{1,2})$'
)

def extract_vehicle_no(text: str | None) -> str | None:
    """Extract and normalize a vehicle registration number from free text."""
    if not text:
        return None
    match = VEHICLE_NO_SEARCH_PATTERN.search(str(text))
    if match:
        normalized = re.sub(r'[\s-]', '', match.group(0)).upper()
        if VEHICLE_NO_NORMALIZED_PATTERN.fullmatch(normalized):
            return normalized
    cleaned = re.sub(r'[\s-]', '', str(text)).upper()
    if VEHICLE_NO_NORMALIZED_PATTERN.fullmatch(cleaned):
        return cleaned
    return None

def _parse_date(value: Any, timezone_name: str, fmt: str = '%d/%m/%Y %H:%M:%S') -> datetime | None:
    if not value: return None
    if isinstance(value, datetime): return value
    try: return datetime.strptime(str(value), fmt).replace(tzinfo=ZoneInfo(timezone_name))
    except (ValueError, TypeError):
        try: return datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        except (ValueError, TypeError): return None

def normalise_vehicle_payload(payload: dict[str, Any], fallback_vehicle_no: str, timezone_name: str = 'Asia/Kolkata') -> VehicleSnapshot:
    data = payload.get('data', payload)
    meta = data.get('terminalPacketMeta') or data.get('terminal_packet_meta') or {}
    last_update = _parse_date(data.get('lu') or data.get('lastUpdate') or data.get('last_update'), timezone_name)
    now = datetime.now(ZoneInfo(timezone_name))
    minutes = (now - last_update.astimezone(ZoneInfo(timezone_name))).total_seconds() / 60 if last_update else None
    due = _parse_date(data.get('subscriptionDue') or data.get('subscription_due'), timezone_name, '%d/%m/%Y')
    since = _parse_date(data.get('since'), timezone_name)
    hours_since = (now - since.astimezone(ZoneInfo(timezone_name))).total_seconds() / 3600.0 if since else None
    days_since = hours_since / 24.0 if hours_since is not None else None
    port = data.get('port')
    speeding_threshold = (
        data.get('speedingThreshold')
        or data.get('speeding_threshold')
        or data.get('speedThreshold')
        or data.get('speed_threshold')
        or data.get('overspeedThreshold')
        or data.get('overspeed_threshold')
        or data.get('speedLimit')
        or data.get('speed_limit')
        or meta.get('speedingThreshold')
        or meta.get('speeding_threshold')
    )
    try:
        speeding_threshold = float(speeding_threshold) if speeding_threshold is not None else None
    except (ValueError, TypeError):
        speeding_threshold = None

    speed = data.get('speed') or meta.get('speed')
    try:
        speed = float(speed) if speed is not None else None
    except (ValueError, TypeError):
        speed = None

    return VehicleSnapshot(
        vehicle_no=str(data.get('vehicleNo') or data.get('vehicle_no') or fallback_vehicle_no).replace(' ', '').upper(),
        device_type=data.get('deviceType') or data.get('device_type'), vehicle_type=data.get('vehicleType') or data.get('vehicle_type'),
        last_update=last_update, minutes_since_last_update=minutes, state=data.get('state'),
        vehicle_status=str(data.get('vehicleStatus', data.get('vehicle_status', '')) or '') or None,
        device_status=str(data.get('deviceStatus', data.get('device_status', '')) or '') or None,
        logger=data.get('logger'), satellites=meta.get('satellites'), battery_connected=meta.get('batteryConnected', meta.get('battery_connected')),
        battery=meta.get('battery'), gsm_signals=meta.get('gsmSignals', meta.get('gsm_signals')),
        subscription_due=due, imei=data.get('imei'), sim_no=data.get('simNo') or data.get('sim_no'),
        operator=data.get('operator'), address=data.get('address'),
        port=port, since=since, hours_since_status=hours_since, days_since_status=days_since,
        speed=speed, speeding_threshold=speeding_threshold,
        raw_payload=payload,
    )
