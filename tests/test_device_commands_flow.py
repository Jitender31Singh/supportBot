from pathlib import Path
from langchain_core.messages import HumanMessage
from trackobit_assistant.adapters.command_registry import YamlCommandRegistry
from trackobit_assistant.adapters.knowledge_base import FileKnowledgeBase
from trackobit_assistant.adapters.session_store_memory import MemorySessionStore
from trackobit_assistant.adapters.ticket_client import LoggingTicketClient
from trackobit_assistant.adapters.vehicle_api import MockVehicleApiClient
from trackobit_assistant.config.settings import Settings
from trackobit_assistant.graph.builder import build_graph
from trackobit_assistant.graph.runtime import Runtime
from trackobit_assistant.services.prompt_repository import PromptRepository


def _make_graph(tmp_path: Path):
    settings = Settings(
        data_dir=tmp_path,
        session_dir=tmp_path / 'sessions',
        upload_dir=tmp_path / 'uploads',
        knowledge_dir=tmp_path / 'kb',
        commands_dir=Path(__file__).parents[1] / 'data' / 'commands'
    )
    settings.ensure_directories()
    store = MemorySessionStore()
    record = store.create_session()
    runtime = Runtime(
        settings=settings,
        session_store=store,
        vehicle_client=MockVehicleApiClient(),
        ticket_client=LoggingTicketClient(),
        command_registry=YamlCommandRegistry(settings.commands_dir),
        knowledge_base=FileKnowledgeBase(settings.knowledge_dir),
        llm=None,
        vision_llm=None,
        prompts=PromptRepository(Path(__file__).parents[1] / 'prompts')
    )
    graph = build_graph(runtime)
    return graph, store, record['session_id']


def test_what_is_the_commands_for_device_type_concox_v5(tmp_path: Path):
    graph, store, session_id = _make_graph(tmp_path)
    state = store.state_for(session_id)
    msg = "what is the commands for device type concox v5?"
    state.update({
        'session_id': session_id,
        'messages': [HumanMessage(content=msg, id='test-user-1')],
        'last_user_message': msg,
        'response': '',
        'sources': [],
        'target_frame_id': None,
        'pending_intents': []
    })

    result = graph.invoke(state, config={'configurable': {'thread_id': session_id}})

    # Should present Concox V5 commands
    assert 'Concox V5' in result['response']
    assert 'STATUS#' in result['response']
    assert 'PARAM#' in result['response']
    # Must NOT lock into diagnosis or wait for vehicle or screenshot
    assert result['awaiting'] == 'none'
    assert result['active_workflow'] == 'none'
    assert result['query_kind'] == 'device_commands'


def test_commands_for_teltonika(tmp_path: Path):
    graph, store, session_id = _make_graph(tmp_path)
    state = store.state_for(session_id)
    msg = "commands for teltonika"
    state.update({
        'session_id': session_id,
        'messages': [HumanMessage(content=msg, id='test-user-1')],
        'last_user_message': msg,
        'response': '',
        'sources': [],
        'target_frame_id': None,
        'pending_intents': []
    })

    result = graph.invoke(state, config={'configurable': {'thread_id': session_id}})

    assert 'Teltonika' in result['response']
    assert 'getver' in result['response']
    assert result['awaiting'] == 'none'


def test_command_query_without_device_type(tmp_path: Path):
    graph, store, session_id = _make_graph(tmp_path)
    state = store.state_for(session_id)
    msg = "what are the device commands?"
    state.update({
        'session_id': session_id,
        'messages': [HumanMessage(content=msg, id='test-user-1')],
        'last_user_message': msg,
        'response': '',
        'sources': [],
        'target_frame_id': None,
        'pending_intents': []
    })

    result = graph.invoke(state, config={'configurable': {'thread_id': session_id}})

    assert 'Please specify the device type' in result['response']
    assert 'Concox V5' in result['response'] or 'Teltonika' in result['response']
    assert result['awaiting'] == 'none'


def test_command_query_as_side_question_during_diagnosis(tmp_path: Path):
    graph, store, session_id = _make_graph(tmp_path)

    # Turn 1: user reports an issue
    state = store.state_for(session_id)
    state.update({
        'session_id': session_id,
        'messages': [HumanMessage(content='location issue', id='msg-1')],
        'last_user_message': 'location issue',
        'response': '',
        'sources': [],
        'target_frame_id': None,
        'pending_intents': []
    })
    result1 = graph.invoke(state, config={'configurable': {'thread_id': session_id}})
    store.save_graph_result(session_id, result1)
    assert result1['awaiting'] == 'vehicle_no'

    # Turn 2: while awaiting vehicle_no, user asks for concox v5 commands
    state2 = store.state_for(session_id)
    cmd_msg = "what is the commands for device type concox v5?"
    state2.update({
        'session_id': session_id,
        'messages': list(result1['messages']) + [HumanMessage(content=cmd_msg, id='msg-2')],
        'last_user_message': cmd_msg,
        'response': '',
        'sources': [],
        'target_frame_id': None,
        'pending_intents': []
    })
    result2 = graph.invoke(state2, config={'configurable': {'thread_id': session_id}})

    # Should answer with the commands and append paused reminder
    assert 'Concox V5' in result2['response']
    assert 'STATUS#' in result2['response']
    # A paused frame exists for diagnosis
    stack = result2.get('workflow_stack') or []
    assert any(f.get('status') in {'paused', 'stale'} for f in stack)
