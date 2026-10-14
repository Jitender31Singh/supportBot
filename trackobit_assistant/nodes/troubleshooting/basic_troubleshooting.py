def make_node(runtime):
    def node(state):
        snapshot=state.get('vehicle_snapshot') or {}
        parked='ignition off' in str(snapshot.get('state') or '').casefold() or state.get('fault_category')=='parked_ignition_off'
        if parked:
            text=runtime.messages.render('basic_troubleshooting_parked.md.j2') if runtime.messages else ''
            if not text:
                text='The latest tracker status says ignition is off. Please move the vehicle to an open area, switch the ignition on, and drive for a few minutes. Then reply “done” so I can fetch a fresh status. A stale location while parked is not enough by itself to call this a hardware fault.'
        else:
            text=runtime.messages.render('basic_troubleshooting.md.j2') if runtime.messages else ''
            if not text:
                text='Please check that the vehicle has power and ignition, move it to an open area with mobile coverage, and let it run for 3–5 minutes. Then reply “done” and I’ll check whether the tracker has reported again.'
        rounds=int(state.get('troubleshoot_rounds') or 0)+(0 if state.get('resume_represent_step') else 1)
        return {'response':text,'awaiting':'troubleshoot_result','troubleshoot_rounds':rounds,'paused_at_step':'waiting for the user to move/check the vehicle and report back','current_step':'basic_troubleshooting'}
    return node
