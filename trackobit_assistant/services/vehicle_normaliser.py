import re
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo
from trackobit_assistant.schemas.models import VehicleSnapshot

# Comprehensive Indian vehicle registration number & fleet asset search pattern
# Standard: State (2 letters) + District (1-2 digits) + optional series/category (0-4 letters) + Number (4 digits)
# BH series: Year (2 digits) + BH + Number (4 digits) + series (1-2 letters)
# Heavy machinery & fleet equipment prefixes (JCB, CAT, TRUCK, etc.) followed by alphanumeric digits
VEHICLE_NO_SEARCH_PATTERN = re.compile(
    r'(?i)\b(?:'
    r'[A-Z]{2}\s*[- ]?\d{1,2}(?:\s*[- ]?[A-Z]+)*\s*[- ]?\d{4}'
    r'|'
    r'\d{2}\s*[- ]?BH\s*[- ]?\d{4}\s*[- ]?[A-Z]{1,2}'
    r'|'
    r'(?:JCB|CAT|TRUCK|TRACTOR|CRANE|TANKER|BUS|VAN|HYDRA|LOADER|DG|GENSET|TRAILER|TIPPER|DUMPER)\s*[- ]?[A-Z0-9]*\d+[A-Z0-9]*'
    r')\b'
)

VEHICLE_PREFIX_SEARCH_PATTERN = re.compile(
    r'(?i)\b(?:vehicle|gaadi|asset|plate)\s*(?:no|num|number)?\s*[:#-]?\s*([A-Za-z0-9-]{3,15})\b'
)

VEHICLE_NO_NORMALIZED_PATTERN = re.compile(
    r'^(?:'
    r'[A-Z]{2}\d{1,2}[A-Z]{0,4}\d{4}'
    r'|'
    r'\d{2}BH\d{4}[A-Z]{1,2}'
    r'|'
    r'(?=.*[A-Z])(?=.*\d)[A-Z0-9-]{3,15}'
    r')$'
)

EXCLUDED_VEHICLE_TERMS = {
    # Device hardware models & series
    'GT06', 'GT06F', 'ET300', 'EV02', 'GS03', 'JV200', 'LT05', 'LT05P',
    'PT06', 'RP01', 'RP01N', 'RP05', 'RP05E', 'S106', 'TK06A', 'TR08A',
    'W15', 'BW09', 'AT06', 'R11', 'R12', 'V5',
    # Telematics protocols & networks
    '2G', '3G', '4G', '5G', 'GPRS', 'GPS', 'GSM',
    # Common conversational / command terms
    'STATUS', 'PARAM', 'RESET', 'SERVER', 'PORT', 'CHECK', 'UPDATE',
    'DEVICE', 'CONFIG', 'COMMAND', 'REPORT', 'REPORTS', 'TEST'
}

def is_valid_vehicle_no(cand: str | None) -> bool:
    """Validate whether a candidate string is a plausible vehicle plate or fleet asset ID."""
    if not cand:
        return False
    norm = re.sub(r'[\s-]', '', str(cand)).upper()
    if norm in EXCLUDED_VEHICLE_TERMS:
        return False
    return bool(VEHICLE_NO_NORMALIZED_PATTERN.fullmatch(norm))

def extract_vehicle_no(text: str | None) -> str | None:
    """Extract and normalize a vehicle registration number or fleet asset ID from free text."""
    if not text:
        return None
    raw_str = str(text).strip()

    # 1. Primary search pattern (Standard Indian RTO, BH series, equipment prefixes)
    match = VEHICLE_NO_SEARCH_PATTERN.search(raw_str)
    if match:
        cand = re.sub(r'[\s-]', '', match.group(0)).upper()
        if is_valid_vehicle_no(cand):
            return cand

    # 2. Contextual prefix search (e.g. "vehicle: ASSET101", "gaadi no HR85G2799")
    prefix_match = VEHICLE_PREFIX_SEARCH_PATTERN.search(raw_str)
    if prefix_match:
        cand = re.sub(r'[\s-]', '', prefix_match.group(1)).upper()
        if is_valid_vehicle_no(cand):
            return cand

    # 3. Direct clean check (single identifier string)
    cleaned = re.sub(r'[\s-]', '', raw_str).upper()
    if is_valid_vehicle_no(cleaned):
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
