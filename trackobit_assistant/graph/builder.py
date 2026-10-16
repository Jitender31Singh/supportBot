from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from trackobit_assistant.graph.state import AssistantState
from trackobit_assistant.graph.runtime import Runtime
from trackobit_assistant.graph import routes
from trackobit_assistant.graph.registry import create_node_registry

def build_graph(runtime: Runtime):
    """Assemble the session graph from the registry and declarative routes."""
    graph=StateGraph(AssistantState)
    for name,fn in create_node_registry(runtime).items():
        graph.add_node(name,fn)
    graph.add_edge(START,'load_session')
    graph.add_edge('load_session','intent_parser')
    graph.add_conditional_edges('intent_parser',routes.route_intent,{
      'greeting_node':'greeting_node','clarify_node':'clarify_node','pause_workflow':'pause_workflow','resume_workflow':'resume_workflow',
      'answer_from_paused':'answer_from_paused','choose_workflow':'choose_workflow','resolution_handler':'resolution_handler',
      'resume_router':'resume_router','query_classifier':'query_classifier'})
    graph.add_conditional_edges('resume_router',lambda s:s.get('resume_target','clarify_node'),{
      'validate_vehicle_no':'validate_vehicle_no','ask_vehicle_no':'ask_vehicle_no','update_dashboard_evidence':'update_dashboard_evidence',
      'ask_dashboard_evidence':'ask_dashboard_evidence','recheck_vehicle_info':'recheck_vehicle_info','basic_troubleshooting':'basic_troubleshooting',
      'process_screenshot':'process_screenshot','present_command':'present_command','resolution_handler':'resolution_handler',
      'resolution_check':'resolution_check','resume_chosen_workflow':'resume_chosen_workflow','stale_resume_handler':'stale_resume_handler',
      'choose_workflow':'choose_workflow','clarify_node':'clarify_node'})
    graph.add_conditional_edges('query_classifier',routes.route_after_query,{
      'rag_answer':'rag_answer','push_frame':'push_frame','clarify_node':'clarify_node','show_device_commands':'show_device_commands'})
    graph.add_conditional_edges('show_device_commands',routes.route_after_device_commands,{
      'reminder_footer':'reminder_footer','save_session':'save_session'})
    graph.add_conditional_edges('rag_answer',routes.route_after_rag,{
      'human_handoff':'human_handoff','reminder_footer':'reminder_footer','save_session':'save_session'})
    graph.add_edge('push_frame','symptom_analyzer')
    graph.add_conditional_edges('symptom_analyzer',routes.route_after_symptoms,{
      'ask_vehicle_no':'ask_vehicle_no','validate_vehicle_no':'validate_vehicle_no'})
    graph.add_edge('ask_vehicle_no','save_session')
    graph.add_conditional_edges('validate_vehicle_no',routes.route_after_validate,{
      'fetch_vehicle_info':'fetch_vehicle_info','human_handoff':'human_handoff','retry_gate':'retry_gate','save_session':'save_session'})
    graph.add_conditional_edges('retry_gate',routes.route_after_retry_gate,{
      'human_handoff':'human_handoff','save_session':'save_session'})
    graph.add_conditional_edges('fetch_vehicle_info',routes.route_after_fetch,{
      'fault_classifier':'fault_classifier','fetch_vehicle_info':'fetch_vehicle_info','human_handoff':'human_handoff'})
    graph.add_conditional_edges('fault_classifier',routes.route_after_fault,{
      'account_advice':'account_advice','create_bug_ticket':'create_bug_ticket','basic_troubleshooting':'basic_troubleshooting',
      'select_command':'select_command','ask_dashboard_evidence':'ask_dashboard_evidence','resolution_check':'resolution_check'})
    graph.add_edge('account_advice','resolution_check')
    graph.add_conditional_edges('create_bug_ticket',routes.route_after_software_ticket,{'human_handoff':'human_handoff','notify_user':'notify_user'})
    graph.add_edge('notify_user','complete_frame')
    graph.add_edge('basic_troubleshooting','save_session')
    graph.add_edge('recheck_vehicle_info','fetch_vehicle_info')
    graph.add_edge('ask_dashboard_evidence','save_session')
    graph.add_conditional_edges('select_command',routes.route_after_select_command,{
      'present_command':'present_command','human_handoff':'human_handoff'})
    graph.add_edge('present_command','save_session')
    graph.add_conditional_edges('process_screenshot',routes.route_after_screenshot,{
      'human_handoff':'human_handoff','analyze_output':'analyze_output','save_session':'save_session'})
    graph.add_conditional_edges('analyze_output',routes.route_after_analyze,{
      'diagnosis_result':'diagnosis_result','resolution_check':'resolution_check','select_command':'select_command'})
    graph.add_edge('diagnosis_result','save_session')
    graph.add_conditional_edges('resolution_handler',routes.route_after_resolution,{
      'close_session':'close_session','select_command':'select_command','save_session':'save_session','human_handoff':'human_handoff'})
    graph.add_edge('resolution_check','save_session')
    graph.add_edge('close_session','complete_frame')
    graph.add_edge('human_handoff','complete_frame')
    graph.add_conditional_edges('complete_frame',routes.route_after_complete,{
      'reminder_footer':'reminder_footer','save_session':'save_session'})
    graph.add_edge('pause_workflow','query_classifier')
    graph.add_conditional_edges('resume_workflow',routes.route_after_resume,{
      'save_session':'save_session','resume_router':'resume_router'})
    graph.add_conditional_edges('stale_resume_handler',routes.route_after_stale_resume,{
      'save_session':'save_session','resume_router':'resume_router'})
    graph.add_edge('choose_workflow','save_session')
    graph.add_edge('answer_from_paused','reminder_footer')
    graph.add_edge('reminder_footer','save_session')
    graph.add_edge('greeting_node','save_session')
    graph.add_conditional_edges('clarify_node',routes.route_after_clarify,{
      'human_handoff':'human_handoff','save_session':'save_session'})
    graph.add_edge('update_dashboard_evidence','fault_classifier')
    graph.add_conditional_edges('resume_chosen_workflow',lambda s:'human_handoff' if s.get('retry_exhausted') else ('resume_workflow' if s.get('workflow_choice_valid') else 'save_session'),{
      'human_handoff':'human_handoff','resume_workflow':'resume_workflow','save_session':'save_session'})
    graph.add_edge('save_session',END)
    return graph.compile(checkpointer=MemorySaver())
