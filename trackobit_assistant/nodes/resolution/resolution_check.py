def make_node(runtime):
    def node(state):
        return {'response':'Is the tracking issue resolved now? Please answer yes or no.','awaiting':'resolution_confirm',
                'paused_at_step':'waiting for a yes/no resolution confirmation','current_step':'resolution_check'}
    return node
