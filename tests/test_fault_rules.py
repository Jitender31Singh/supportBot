from trackobit_assistant.services.fault_rules import classify_fault
from trackobit_assistant.schemas.models import FaultCategory

def test_inactive_device_is_account_issue():
    result=classify_fault({'vehicle_status':'Inactive','device_status':'Active'},None)
    assert result.category == FaultCategory.ACCOUNT_ISSUE

def test_ignition_off_and_stale_is_not_automatically_hardware():
    result=classify_fault({'state':'Ignition off','minutes_since_last_update':90,'vehicle_status':'Active','device_status':'Active'},None)
    assert result.category == FaultCategory.PARKED_IGNITION_OFF

def test_weak_gsm_is_hardware_issue():
    result=classify_fault({'state':'Ignition on','minutes_since_last_update':90,'gsm_signals':1,'battery_connected':True,'satellites':8,'vehicle_status':'Active','device_status':'Active'},'still not updating')
    assert result.category == FaultCategory.HARDWARE_ISSUE

def test_fresh_api_and_stale_dashboard_is_software_issue():
    result=classify_fault({'minutes_since_last_update':2,'vehicle_status':'Active','device_status':'Active'},'dashboard shows stale location')
    assert result.category == FaultCategory.SOFTWARE_ISSUE

def test_fresh_api_and_buffering_is_software_issue():
    result = classify_fault({'minutes_since_last_update': 0.1, 'vehicle_status': 'Active', 'device_status': 'Active'}, 'device is buffering')
    assert result.category == FaultCategory.SOFTWARE_ISSUE
