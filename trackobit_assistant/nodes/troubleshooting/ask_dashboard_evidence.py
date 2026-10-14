def make_node(runtime):
    def node(state):
        return {'response':'The tracker API looks reasonably fresh, so I need to distinguish a device problem from a dashboard display problem. What does TrackoBit show for this vehicle (last location/time), and is that different from the latest status here? You can attach a screenshot.','awaiting':'dashboard_evidence',
                'paused_at_step':'waiting for the dashboard’s shown location/time or a screenshot','current_step':'ask_dashboard_evidence'}
    return node
