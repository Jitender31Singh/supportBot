def make_node(runtime):
    def node(state):
        return {'recheck_requested':True,'response':'','awaiting':'none','current_step':'fetch_vehicle_info'}
    return node
