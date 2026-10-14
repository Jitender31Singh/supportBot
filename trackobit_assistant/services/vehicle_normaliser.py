from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo
from trackobit_assistant.schemas.models import VehicleSnapshot

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
    return VehicleSnapshot(
        vehicle_no=str(data.get('vehicleNo') or data.get('vehicle_no') or fallback_vehicle_no).replace(' ', '').upper(),
        device_type=data.get('deviceType') or data.get('device_type'), vehicle_type=data.get('vehicleType') or data.get('vehicle_type'),
        last_update=last_update, minutes_since_last_update=minutes, state=data.get('state'),
        vehicle_status=str(data.get('vehicleStatus', data.get('vehicle_status', '')) or '') or None,
        device_status=str(data.get('deviceStatus', data.get('device_status', '')) or '') or None,
        logger=data.get('logger'), satellites=meta.get('satellites'), battery_connected=meta.get('batteryConnected', meta.get('battery_connected')),
        battery=meta.get('battery'), gsm_signals=meta.get('gsmSignals', meta.get('gsm_signals')),
        subscription_due=due, imei=data.get('imei'), sim_no=data.get('simNo') or data.get('sim_no'),
        operator=data.get('operator'), address=data.get('address'), raw_payload=payload,
    )
