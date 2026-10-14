def make_node(runtime):
    def node(state):
        snap=state.get('vehicle_snapshot') or {}
        bits=[]
        if snap.get('subscription_due'): bits.append(f"subscription due date: {snap.get('subscription_due')}")
        if snap.get('vehicle_status'): bits.append(f"vehicle status: {snap.get('vehicle_status')}")
        if snap.get('device_status'): bits.append(f"device status: {snap.get('device_status')}")
        detail='; '.join(bits) or 'an account/device activation status needs attention'
        return {'response':f"The status check points to an account or activation issue ({detail}). Please ask your account administrator to verify the subscription and vehicle/device activation. I’ll check whether there’s anything else we need to do.",
                'awaiting':'resolution_confirm','paused_at_step':'waiting to confirm whether the tracking issue is resolved','current_step':'resolution_check'}
    return node
