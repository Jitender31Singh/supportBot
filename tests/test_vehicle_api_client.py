import httpx
from trackobit_assistant.adapters.vehicle_api import HttpVehicleApiClient, SAMPLE_PAYLOAD
from trackobit_assistant.config.settings import Settings

def test_http_vehicle_client_falls_back_to_mock_when_no_url():
    settings = Settings(vehicle_api_url_template=None, vehicle_api_base_url=None)
    client = HttpVehicleApiClient(settings)
    snap = client.get_vehicle("HR85G2799")
    assert snap.vehicle_no == "HR85G2799"
    assert snap.device_type == "Concox V5"

def test_http_vehicle_client_calls_templated_url_with_auth_token(monkeypatch):
    captured_request = {}

    def mock_handler(request: httpx.Request):
        captured_request['url'] = str(request.url)
        captured_request['headers'] = dict(request.headers)
        return httpx.Response(200, json=SAMPLE_PAYLOAD)

    transport = httpx.MockTransport(mock_handler)
    real_client_init = httpx.Client.__init__

    def patched_init(self, *args, **kwargs):
        kwargs['transport'] = transport
        real_client_init(self, *args, **kwargs)

    monkeypatch.setattr(httpx.Client, "__init__", patched_init)

    settings = Settings(
        vehicle_api_url_template="https://www.tbtrack.in/gps/ajax/v3/vehicle/detail/{vehicle_number}",
        api_auth_token="test-jwt-token-12345",
    )
    client = HttpVehicleApiClient(settings)
    snap = client.get_vehicle("DL01AB1234")

    assert captured_request['url'] == "https://www.tbtrack.in/gps/ajax/v3/vehicle/detail/DL01AB1234"
    assert captured_request['headers'].get('authorization') == "Bearer test-jwt-token-12345"
    assert snap.vehicle_no == "HR85G2799"  # From sample payload or normalized


import pytest
from trackobit_assistant.adapters.vehicle_api import MockVehicleApiClient, VehicleNotFoundError

def test_mock_vehicle_client_raises_for_non_existent_vehicle():
    client = MockVehicleApiClient()
    with pytest.raises(VehicleNotFoundError):
        client.get_vehicle("HR85G2790")

def test_http_vehicle_client_raises_vehicle_not_found_on_406(monkeypatch):
    def mock_handler(request: httpx.Request):
        return httpx.Response(406, json={"status": "NOT_ACCEPTABLE", "code": 406, "message": "Vehicle does not exists or active"})

    transport = httpx.MockTransport(mock_handler)
    real_client_init = httpx.Client.__init__

    def patched_init(self, *args, **kwargs):
        kwargs['transport'] = transport
        real_client_init(self, *args, **kwargs)

    monkeypatch.setattr(httpx.Client, "__init__", patched_init)

    settings = Settings(
        vehicle_api_url_template="https://www.tbtrack.in/gps/ajax/v3/vehicle/detail/{vehicle_number}",
        api_auth_token="test-token",
    )
    client = HttpVehicleApiClient(settings)
    with pytest.raises(VehicleNotFoundError) as exc_info:
        client.get_vehicle("HR85G2790")
    assert "Vehicle does not exists" in str(exc_info.value)
