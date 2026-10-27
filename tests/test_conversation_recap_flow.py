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

class FreshMockVehicleApiClient(MockVehicleApiClient):
    def get_vehicle(self, vehicle_no: str):
        snap = super().get_vehicle(vehicle_no)
        snap.minutes_since_last_update = 0.8
        return snap

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
        vehicle_client=FreshMockVehicleApiClient(),
        ticket_client=LoggingTicketClient(),
        command_registry=YamlCommandRegistry(settings.commands_dir),
        knowledge_base=FileKnowledgeBase(settings.knowledge_dir),
        llm=None,
        vision_llm=None,
        prompts=PromptRepository(Path(__file__).parents[1] / 'prompts')
    )
    graph = build_graph(runtime)
    return graph, store, record['session_id']


def test_what_i_have_asked_after_vehicle_check(tmp_path: Path):
    graph, store, session_id = _make_graph(tmp_path)
    state = store.state_for(session_id)

    # Turn 1: user asks to check configuration for vehicle HR85G2799
    msg1 = "i wanna check the configuration for my vehicle HR85G2799"
    state.update({
        'session_id': session_id,
        'messages': [HumanMessage(content=msg1, id='msg-1')],
        'last_user_message': msg1,
        'response': '',
        'sources': [],
        'target_frame_id': None,
        'pending_intents': []
    })
    res1 = graph.invoke(state, config={'configurable': {'thread_id': session_id}})
    store.save_graph_result(session_id, res1)

    # Turn 2: confirm port
    state2 = store.state_for(session_id)
    msg2 = "yes"
    state2.update({
        'session_id': session_id,
        'messages': list(res1['messages']) + [HumanMessage(content=msg2, id='msg-2')],
        'last_user_message': msg2,
        'response': '',
        'sources': [],
        'target_frame_id': None,
        'pending_intents': []
    })
    res2 = graph.invoke(state2, config={'configurable': {'thread_id': session_id}})
    store.save_graph_result(session_id, res2)

    # Turn 3: confirm device model
    state3 = store.state_for(session_id)
    msg3 = "yes"
    state3.update({
        'session_id': session_id,
        'messages': list(res2['messages']) + [HumanMessage(content=msg3, id='msg-3')],
        'last_user_message': msg3,
        'response': '',
        'sources': [],
        'target_frame_id': None,
        'pending_intents': []
    })
    res3 = graph.invoke(state3, config={'configurable': {'thread_id': session_id}})
    store.save_graph_result(session_id, res3)

    # Summary has been presented, awaiting is none
    assert res3['awaiting'] == 'none'
    assert 'HR85G2799' in res3['response']

    # Turn 4: user asks "what i have asked?"
    state4 = store.state_for(session_id)
    msg4 = "what i have asked?"
    state4.update({
        'session_id': session_id,
        'messages': list(res3['messages']) + [HumanMessage(content=msg4, id='msg-4')],
        'last_user_message': msg4,
        'response': '',
        'sources': [],
        'target_frame_id': None,
        'pending_intents': []
    })
    res4 = graph.invoke(state4, config={'configurable': {'thread_id': session_id}})

    # Must NOT raise ticket or escalate to human handoff!
    assert 'Ticket' not in res4['response']
    assert 'handing this over' not in res4['response']
    assert res4.get('handoff_reason') is None

    # Must recall what user asked about HR85G2799
    assert 'HR85G2799' in res4['response']
    assert 'check the configuration' in res4['response'].lower() or 'configuration' in res4['response'].lower()


def test_recap_query_hinglish(tmp_path: Path):
    graph, store, session_id = _make_graph(tmp_path)
    state = store.state_for(session_id)

    # Turn 1: user reports gps problem
    msg1 = "GPS not working for HR85G2799"
    state.update({
        'session_id': session_id,
        'messages': [HumanMessage(content=msg1, id='msg-1')],
        'last_user_message': msg1,
        'response': '',
        'sources': [],
        'target_frame_id': None,
        'pending_intents': []
    })
    res1 = graph.invoke(state, config={'configurable': {'thread_id': session_id}})
    store.save_graph_result(session_id, res1)

    # Turn 2: user asks in Hindi/Hinglish "maine kya pucha?"
    state2 = store.state_for(session_id)
    msg2 = "maine kya pucha?"
    state2.update({
        'session_id': session_id,
        'messages': list(res1['messages']) + [HumanMessage(content=msg2, id='msg-2')],
        'last_user_message': msg2,
        'response': '',
        'sources': [],
        'target_frame_id': None,
        'pending_intents': []
    })
    res2 = graph.invoke(state2, config={'configurable': {'thread_id': session_id}})

    # Must not raise ticket
    assert 'Ticket' not in res2['response']
    assert 'GPS not working for HR85G2799' in res2['response']
