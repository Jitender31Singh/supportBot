from trackobit_assistant.services.workflow_stack import resume, complete

def make_node(runtime):
    def node(state):
        text=(state.get('last_user_message') or '').strip().casefold()
        target=state.get('pending_resume_frame_id') or state.get('target_frame_id')
        stack=state.get('workflow_stack') or []
        if text in {'yes','y','still happens','still not working','same issue','yes it does'} or text.startswith('yes '):
            stack,active=resume(stack,target,state.get('active_frame_id')) if target else (stack,None)
            frame=next((f for f in stack if f.get('frame_id')==active),None)
            context=(frame or {}).get('context') or {}
            step=(frame or {}).get('paused_at_step') or (frame or {}).get('current_node') or 'the last support step'
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
                'target_frame_id':active,'pending_resume_frame_id':None,'resume_prefix':f"Thanks for confirming. I’ll resume at: {step}.",
                'resume_announcement':True,'resume_represent_step':True,
                'response':'I’ll continue the existing workflow from the saved step.'}
        if text in {'no','n','fixed','resolved','not anymore','problem gone'} or text.startswith('no '):
            stack=complete(stack,target,'abandoned','User confirmed the old issue no longer applies after stale resume check.')
            return {'workflow_stack':stack,'active_frame_id':None,'active_workflow':'none','awaiting':'none','pending_resume_frame_id':None,
                'response':'Understood. I’ve closed that paused workflow as no longer relevant. Tell me if you need help with anything else.'}
        return {'response':'Please reply yes if the same issue still occurs or no if it is no longer happening.','awaiting':'stale_resume_confirm',
                'current_step':'stale_resume_handler','pending_resume_frame_id':target}
    return node
