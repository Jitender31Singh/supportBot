from trackobit_assistant.services.summarizer import summarize_session

def make_node(runtime):
    def node(state):
        reason=state.get('handoff_reason') or state.get('retry_step') or 'low_confidence_or_unknown_issue'
        summary=summarize_session(state)
        try:
            ticket=runtime.ticket_client.create(summary=summary,reason=str(reason),metadata={'session_id':state.get('session_id'),
                'vehicle_no':state.get('vehicle_no'),'snapshot':state.get('vehicle_snapshot'),'assigned_to':runtime.settings.assign_to_support_user})
            info=ticket.model_dump(mode='json')
            response=f"I’m handing this over to the support team because {str(reason).replace('_',' ')}. Ticket **{ticket.ticket_id}** has been created for follow-up. I’ve included the details collected in this chat."
        except Exception as exc:
            info={'ticket_id':None,'status':'failed','reason':type(exc).__name__}
            response='I need a support specialist to take over this case. The automatic ticket system is unavailable, but the issue details are retained in this session.'
        return {'ticket_info':info,'handoff_reason':str(reason),'response':response,'active_workflow':'handoff','awaiting':'none','summary':summary,'current_step':'complete_frame'}
    return node
