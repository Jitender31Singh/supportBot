def make_node(runtime):
    def node(state):
        return {'response':state.get('response') or 'The support team has been notified.','awaiting':'none'}
    return node
