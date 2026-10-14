from trackobit_assistant.services.summarizer import summarize_session

def make_node(runtime):
    def node(state):
        summary=summarize_session(state)
        metadata={'session_id':state.get('session_id'),'vehicle_no':state.get('vehicle_no'),'device_type':(state.get('vehicle_snapshot') or {}).get('device_type'),
                  'snapshot':state.get('vehicle_snapshot'),'dashboard_evidence':state.get('dashboard_evidence'),'assigned_to':runtime.settings.assign_to_support_user}
        try:
            ticket=runtime.ticket_client.create(summary=summary,reason='software_issue',metadata=metadata)
            info=ticket.model_dump(mode='json')
            return {'ticket_info':info,'response':f"The vehicle API has a fresh update, but the dashboard is reported as stale, so this looks like a software/data-display issue. I’ve created support ticket **{ticket.ticket_id}** and assigned it to the support team. You don’t need to repeat the details from this chat.",
                    'handoff_reason':'software_issue','current_step':'complete_frame'}
        except Exception as exc:
            return {'errors':(state.get('errors') or [])+[f'ticket_create:{type(exc).__name__}'],'handoff_reason':'software_ticket_create_failed',
                    'response':'This appears to be a software issue, but I could not create the internal ticket automatically. I’m flagging the case for support with the information collected so far.'}
    return node
