import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception
from trackobit_assistant.config.settings import Settings
from trackobit_assistant.schemas.models import VehicleSnapshot
from trackobit_assistant.services.vehicle_normaliser import normalise_vehicle_payload


class VehicleNotFoundError(Exception):
    """Raised when a vehicle registration number does not exist or is not active in the system."""
    pass


SAMPLE_PAYLOAD = {
  'status':'OK','code':200,'data': {
    'ouid':'6a95569b232ba163cdceded9','state':'Ignition off','vehicleNo':'HR85G2799',
    'clientUsername':'india_trackers09','transporterUsername':'sunilsingh123','companyName':'SUNIL SINGH',
    'lu':'12/10/2026 16:16:39','since':'12/10/2026 15:30:15','added':'31/08/2026',
    'subscriptionDue':'31/08/2027','subscriptionStart':'31/08/2026','odometer':60222,
    'deviceType':'Concox V5','vehicleType':'personalcar','lock':False,'status':True,'logger':True,
    'deviceStatus':'Active','vehicleStatus':'Active','imei':'355172108792241','simNo':'5754226331882',
    'operator':'Airtel Gprs','address':'Ring Rd Dubli, Dubli, Haryana 133102, India',
    'terminalPacketMeta': {'satellites':15,'batteryConnected':True,'battery':100,'gsmSignals':4,
      'pLoc':[76.87536166666666,30.246713333333336],'e_battery':0,'panic':False,'parked':False,
      'tempered':False,'elockBatteryLow':False,'iccid':'89911025034039635919'},
    'ignitionNotConnected':False,'ac':False,'port':8503,'ulipVahanStatus':0,'cloudBackup':False,'autoRenewal':False
  }
}

class MockVehicleApiClient:
    def __init__(self, timezone_name: str = 'Asia/Kolkata') -> None:
        self.timezone_name = timezone_name

    def get_vehicle(self, vehicle_no: str) -> VehicleSnapshot:
        v_upper = str(vehicle_no).replace(' ', '').replace('-', '').upper()
        if v_upper in {'NOTFOUND', 'HR85G2790', 'INVALID', 'UNKNOWN'}:
            raise VehicleNotFoundError(f"Vehicle '{vehicle_no}' does not exist or is not active in the system.")
        payload = {**SAMPLE_PAYLOAD, 'data': {**SAMPLE_PAYLOAD['data'], 'vehicleNo': vehicle_no.upper()}}
        return normalise_vehicle_payload(payload, fallback_vehicle_no=vehicle_no, timezone_name=self.timezone_name)

def _retryable_http_error(exc: BaseException) -> bool:
    if isinstance(exc, VehicleNotFoundError):
        return False
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code == 429 or exc.response.status_code >= 500
    return isinstance(exc, (httpx.TimeoutException, httpx.NetworkError))

class HttpVehicleApiClient:
    def __init__(self, settings: Settings):
        self.settings = settings

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.2,min=0.2,max=1.0), retry=retry_if_exception(_retryable_http_error), reraise=True)
    def get_vehicle(self, vehicle_no: str) -> VehicleSnapshot:
        template = (self.settings.vehicle_api_url_template or '').strip()
        base_url = (self.settings.vehicle_api_base_url or '').strip()

        if not template and not base_url:
            return MockVehicleApiClient(self.settings.app_timezone).get_vehicle(vehicle_no)

        if template:
            url = template.format(vehicle_number=vehicle_no, vehicle_no=vehicle_no)
        else:
            url = base_url.rstrip('/') + self.settings.vehicle_api_path.format(vehicle_no=vehicle_no)

        headers = {'Accept': 'application/json'}
        token = (self.settings.api_auth_token or self.settings.vehicle_api_key or '').strip()
        if token:
            auth_val = token if token.lower().startswith('bearer ') else f'Bearer {token}'
            headers['Authorization'] = auth_val

        with httpx.Client(timeout=self.settings.vehicle_api_timeout_seconds) as client:
            response = client.get(url, headers=headers)
            if response.status_code in (404, 406):
                try:
                    data = response.json()
                    msg = data.get('message') or data.get('status') or f"Vehicle '{vehicle_no}' does not exist or is not active."
                except Exception:
                    msg = response.text or f"Vehicle '{vehicle_no}' does not exist."
                raise VehicleNotFoundError(msg)
            response.raise_for_status()
            payload = response.json()
            if isinstance(payload, dict):
                if payload.get('code') in (404, 406) or str(payload.get('status')).upper() in ('NOT_ACCEPTABLE', 'NOT_FOUND'):
                    msg = payload.get('message') or f"Vehicle '{vehicle_no}' does not exist or is not active."
                    raise VehicleNotFoundError(msg)

        return normalise_vehicle_payload(payload, fallback_vehicle_no=vehicle_no, timezone_name=self.settings.app_timezone)
