from trackobit_assistant.services.workflow_stack import resume

def make_node(runtime):
    def node(state):
        target=state.get('target_frame_id') or state.get('pending_resume_frame_id')
        stack=state.get('workflow_stack') or []
        if not target:
            candidates=[f for f in stack if f.get('status') in {'paused','stale'}]
            target=candidates[-1].get('frame_id') if candidates else state.get('active_frame_id')
        original=next((f for f in stack if f.get('frame_id')==target),None)
        if not original:
            return {'response':'I couldn’t identify which paused issue to resume. Please tell me which vehicle or issue you mean.','awaiting':'none'}
        if original.get('status') == 'stale' and state.get('awaiting') != 'stale_resume_confirm':
            updates={}
            stack=[dict(frame) for frame in stack]
            original=next((frame for frame in stack if frame.get('frame_id')==target),original)
            original_context=original.get('context') or {}
            vehicle_no=original_context.get('vehicle_no') or state.get('vehicle_no')
            if vehicle_no:
                try:
                    snap=runtime.vehicle_client.get_vehicle(vehicle_no).model_dump(mode='json')
                    updates['vehicle_snapshot']=snap
                    updates['snapshot_history']=(list(state.get('snapshot_history') or [])+[snap])[-10:]
                    original_context=dict(original.get('context') or {})
                    original_context.update({'vehicle_no':vehicle_no,'vehicle_snapshot':snap,'snapshot_history':updates['snapshot_history']})
                    original['context']=original_context
                    refreshed='I refreshed the latest vehicle status.'
                except Exception:
                    refreshed='I couldn’t refresh the latest vehicle status just now.'
            else: refreshed='I don’t have a vehicle number saved for a fresh status check.'
            step=original.get('paused_at_step') or original.get('current_node') or original.get('awaiting') or 'the previous support step'
            updates.update({'workflow_stack':stack,'vehicle_no':vehicle_no,'pending_resume_frame_id':target,'target_frame_id':target,'active_frame_id':None,'active_workflow':'none',
                'awaiting':'stale_resume_confirm','current_step':'stale_resume_handler',
                'response':f"This support issue was paused for a while. {refreshed} Does the same problem still happen? Reply yes or no. It was paused at: {step}.",
                'paused_at_step':step})
            return updates
        stack,active=resume(stack,target,state.get('active_frame_id'))
        frame=next((f for f in stack if f.get('frame_id')==active),None)
        context=(frame or {}).get('context') or {}
        user_text=(state.get('last_user_message') or '').strip().casefold()
        resume_only=user_text in {'continue','resume','go back','back to the issue','back to my issue','continue the previous issue','1','2','3','4','5'} or state.get('intent')=='resume_request' or state.get('workflow_choice_valid') is True
        step=(frame or {}).get('paused_at_step') or (frame or {}).get('current_node') or (frame or {}).get('awaiting') or 'the current support step'
        announcement = runtime.messages.render('resume_announce.md.j2', paused_at_step=step) if runtime.messages else ''
        if not announcement:
            announcement = f"Picking up where we paused: {step}."
        return {'workflow_stack':stack,'active_frame_id':active,'active_workflow':(frame or {}).get('type','diagnosis'),
                'awaiting':(frame or {}).get('awaiting','none'),'current_step':(frame or {}).get('current_node'),
                'current_command':context.get('current_command',state.get('current_command')),
                'command_history':context.get('command_history',state.get('command_history') or []),
                'retry_counters':context.get('retry_counters',state.get('retry_counters') or {}),
                'vehicle_no':context.get('vehicle_no',state.get('vehicle_no')),
                'vehicle_snapshot':context.get('vehicle_snapshot',state.get('vehicle_snapshot')),
                'snapshot_history':context.get('snapshot_history',state.get('snapshot_history') or []),
                'dashboard_evidence':context.get('dashboard_evidence',state.get('dashboard_evidence')),
                'symptoms':context.get('symptoms',state.get('symptoms') or {}),
                'fault_category':context.get('fault_category',state.get('fault_category')),
                'fault_evidence':context.get('fault_evidence',state.get('fault_evidence') or []),
                'troubleshoot_rounds':context.get('troubleshoot_rounds',state.get('troubleshoot_rounds') or 0),
                'ticket_info':context.get('ticket_info',state.get('ticket_info')),
                'target_frame_id':active,'pending_resume_frame_id':None,'resume_prefix':announcement,
                'resume_announcement':True,'resume_represent_step':resume_only,'workflow_choice_valid':False,'response':'Continue from the paused step.'}
    return node
