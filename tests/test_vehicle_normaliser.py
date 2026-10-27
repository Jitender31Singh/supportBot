from trackobit_assistant.services.vehicle_normaliser import (
    normalise_vehicle_payload,
    extract_vehicle_no,
    VEHICLE_NO_SEARCH_PATTERN,
    VEHICLE_NO_NORMALIZED_PATTERN
)

def test_vehicle_payload_normalises_and_preserves_raw():
    payload = {
        'status': 'OK', 'code': 200, 'data': {
            'vehicleNo': 'HR85G2799', 'deviceType': 'Concox V5', 'lu': '12/10/2026 16:16:39',
            'state': 'Ignition off', 'deviceStatus': 'Active', 'vehicleStatus': 'Active', 'logger': True,
            'subscriptionDue': '31/08/2027', 'terminalPacketMeta': {'satellites': 15, 'batteryConnected': True, 'battery': 100, 'gsmSignals': 4}
        }
    }
    snap = normalise_vehicle_payload(payload, 'HR85G2799')
    assert snap.vehicle_no == 'HR85G2799'
    assert snap.device_type == 'Concox V5'
    assert snap.satellites == 15
    assert snap.raw_payload['data']['vehicleNo'] == 'HR85G2799'

def test_extract_vehicle_no_various_formats():
    cases = [
        ('HR85G2799', 'HR85G2799'),
        ('HR85G2799 this', 'HR85G2799'),
        ('HR 85 G 2799', 'HR85G2799'),
        ('HR-85-G-2799', 'HR85G2799'),
        ('DL 1C AA 1111', 'DL1CAA1111'),
        ('DL 01 C AA 1111', 'DL01CAA1111'),
        ('DL01A1234', 'DL01A1234'),
        ('UP-16-Z-1234', 'UP16Z1234'),
        ('MH 12 AB 1234', 'MH12AB1234'),
        ('KA 03 1234', 'KA031234'),
        ('22BH1234AA', '22BH1234AA'),
        ('22 BH 1234 AA', '22BH1234AA'),
        ('that is HR85G2791', 'HR85G2791'),
        ('another vehicle number that is HR85G2791', 'HR85G2791'),
        ('my car HR85G2799 is stopped', 'HR85G2799'),
        ('give me details of all the employees', None),
        ('hi', None),
        ('what is the command for concox', None),
    ]
    for text, expected in cases:
        assert extract_vehicle_no(text) == expected, f"Failed for text '{text}': got {extract_vehicle_no(text)}, expected {expected}"
