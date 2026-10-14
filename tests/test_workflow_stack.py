from trackobit_assistant.services.workflow_stack import push, pause_active, resume, complete

def test_pause_push_resume_complete_preserves_frame():
    stack,first=push([],None,'diagnosis',{'vehicle_no':'HR85G2799'})
    stack,_=pause_active(stack,first,'waiting for screenshot')
    assert next(f for f in stack if f['frame_id']==first)['status']=='paused'
    stack,second=push(stack,None,'diagnosis',{})
    stack,active=resume(stack,first,second)
    assert active==first
    assert next(f for f in stack if f['frame_id']==second)['status']=='paused'
    stack=complete(stack,first,'resolved','fixed')
    assert next(f for f in stack if f['frame_id']==first)['status']=='done'


def test_ambiguous_workflow_choice_does_not_guess_when_multiple_frames():
    from trackobit_assistant.nodes.workflow_control.target_helpers import choose_target
    state={'last_user_message':'continue','workflow_stack':[
        {'frame_id':'f1','type':'diagnosis','status':'paused','paused_at_step':'waiting for screenshot'},
        {'frame_id':'f2','type':'diagnosis','status':'paused','paused_at_step':'waiting for vehicle number'},
    ]}
    assert choose_target(state) is None
    state['last_user_message']='2'
    assert choose_target(state)=='f2'
