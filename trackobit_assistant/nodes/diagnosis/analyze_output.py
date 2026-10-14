import logging
from trackobit_assistant.services.output_analyzer import analyze_command_output

logger = logging.getLogger('trackobit_assistant.nodes.analyze_output')

def make_node(runtime):
    def node(state):
        session_id = state.get('session_id', '-')
        command=state.get('current_command') or {}
        parsed=state.get('parsed_command_output') or {}
        result=analyze_command_output(command,parsed)
        logger.info(
            f"[ANALYZE_OUTPUT] Analyzed output for command '{command.get('command')}': verdict='{result['verdict']}', finding='{result['finding']}'",
            extra={'session_id': session_id}
        )
        history=list(state.get('command_history') or [])
        history.append({'command_id':command.get('id'),'command':command.get('command'),'parsed_output':parsed,'verdict':result['verdict'],
            'finding':result['finding'],'advice':result['advice'],'evidence':result['evidence'],'next_if_inconclusive':command.get('next_if_inconclusive',[])})
        return {'command_history':history,'command_verdict':result['verdict'],'command_analysis':result,'response':'','current_step':'analyze_output'}
    return node

