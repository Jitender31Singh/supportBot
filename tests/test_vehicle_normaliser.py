from trackobit_assistant.services.vehicle_normaliser import normalise_vehicle_payload

def test_vehicle_payload_normalises_and_preserves_raw():
    payload={'status':'OK','code':200,'data':{'vehicleNo':'HR85G2799','deviceType':'Concox V5','lu':'12/10/2026 16:16:39',
        'state':'Ignition off','deviceStatus':'Active','vehicleStatus':'Active','logger':True,
        'subscriptionDue':'31/08/2027','terminalPacketMeta':{'satellites':15,'batteryConnected':True,'battery':100,'gsmSignals':4}}}
    snap=normalise_vehicle_payload(payload,'HR85G2799')
    assert snap.vehicle_no=='HR85G2799'
    assert snap.device_type=='Concox V5'
    assert snap.satellites==15
    assert snap.raw_payload['data']['vehicleNo']=='HR85G2799'
