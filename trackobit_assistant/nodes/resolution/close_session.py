from trackobit_assistant.services.summarizer import summarize_session

def make_node(runtime):
    def node(state):
        return {'resolved':True,'summary':summarize_session(state),'awaiting':'none','active_workflow':'none','current_step':'complete_frame'}
    return node
