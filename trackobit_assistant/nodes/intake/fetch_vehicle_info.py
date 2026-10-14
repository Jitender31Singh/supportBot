import logging
import httpx

logger = logging.getLogger('trackobit_assistant.nodes.fetch_vehicle_info')

def make_node(runtime):
    def node(state):
        session_id = state.get('session_id', '-')
        vehicle=state.get('vehicle_no')
        if not vehicle:
            logger.warning("[FETCH_VEHICLE] vehicle_no is missing", extra={'session_id': session_id})
            return {'api_ok':False,'api_error':'vehicle_no_missing','response':'I still need the vehicle number before I can check the tracker.','awaiting':'vehicle_no'}
        try:
            logger.info(f"[FETCH_VEHICLE] Fetching status for vehicle '{vehicle}'...", extra={'session_id': session_id})
            snapshot=runtime.vehicle_client.get_vehicle(vehicle)
            previous=list(state.get('snapshot_history') or [])
            snapshot_json=snapshot.model_dump(mode='json')
            logger.info(
                f"[FETCH_VEHICLE] Success: device_type='{snapshot_json.get('device_type')}', ignition='{snapshot_json.get('ignition')}', last_update='{snapshot_json.get('last_update')}'",
                extra={'session_id': session_id}
            )
            return {'vehicle_snapshot':snapshot_json,'snapshot_history':(previous+[snapshot_json])[-10:],'api_ok':True,'api_error':None,'response':'','current_step':'fault_classifier'}
        except (httpx.HTTPError, ValueError, KeyError, TimeoutError) as exc:
            logger.error(f"[FETCH_VEHICLE] API call failed for '{vehicle}': {type(exc).__name__}: {exc}", extra={'session_id': session_id})
            return {'api_ok':False,'api_error':type(exc).__name__,'errors':(state.get('errors') or [])+[f'vehicle_api:{type(exc).__name__}'],
                    'response':'I couldn’t reach the vehicle status service right now. I’ll try again; if it stays unavailable, I’ll send this to support.'}
    return node

