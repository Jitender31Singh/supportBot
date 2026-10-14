"""Graph smoke tests execute in the project venv where LangGraph is installed."""
import pytest
pytest.importorskip('langgraph')
pytest.importorskip('langchain_core')

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


def test_graph_greeting_round_trip(tmp_path: Path):
    settings = Settings(data_dir=tmp_path, session_dir=tmp_path / 'sessions', upload_dir=tmp_path / 'uploads',
        knowledge_dir=tmp_path / 'kb', commands_dir=Path(__file__).parents[1] / 'data' / 'commands')
    settings.ensure_directories()
    store = MemorySessionStore()
    record = store.create_session()
    runtime = Runtime(settings=settings, session_store=store, vehicle_client=MockVehicleApiClient(),
        ticket_client=LoggingTicketClient(), command_registry=YamlCommandRegistry(settings.commands_dir),
        knowledge_base=FileKnowledgeBase(settings.knowledge_dir), llm=None, vision_llm=None,
        prompts=PromptRepository(Path(__file__).parents[1] / 'prompts'))
    graph = build_graph(runtime)
    state = store.state_for(record['session_id'])
    state.update({'session_id': record['session_id'], 'messages': [HumanMessage(content='Hi', id='test-user-1')],
                  'last_user_message': 'Hi', 'response': '', 'sources': [], 'target_frame_id': None,
                  'pending_intents': []})
    result = graph.invoke(state, config={'configurable': {'thread_id': record['session_id']}})
    assert 'TrackoBit support assistant' in result['response']
    assert result['messages'][-1].content == result['response']


def test_graph_diagnosis_location_flow(tmp_path: Path):
    settings = Settings(data_dir=tmp_path, session_dir=tmp_path / 'sessions', upload_dir=tmp_path / 'uploads',
        knowledge_dir=tmp_path / 'kb', commands_dir=Path(__file__).parents[1] / 'data' / 'commands')
    settings.ensure_directories()
    store = MemorySessionStore()
    record = store.create_session()
    runtime = Runtime(settings=settings, session_store=store, vehicle_client=MockVehicleApiClient(),
        ticket_client=LoggingTicketClient(), command_registry=YamlCommandRegistry(settings.commands_dir),
        knowledge_base=FileKnowledgeBase(settings.knowledge_dir), llm=None, vision_llm=None,
        prompts=PromptRepository(Path(__file__).parents[1] / 'prompts'))
    graph = build_graph(runtime)

    # Turn 1: user reports location issue
    state = store.state_for(record['session_id'])
    state.update({'session_id': record['session_id'], 'messages': [HumanMessage(content='location issue', id='test-user-1')],
                  'last_user_message': 'location issue', 'response': '', 'sources': [], 'target_frame_id': None,
                  'pending_intents': []})
    result1 = graph.invoke(state, config={'configurable': {'thread_id': record['session_id']}})
    store.save_graph_result(record['session_id'], result1)

    assert result1['awaiting'] == 'vehicle_no'
    assert result1['active_workflow'] == 'diagnosis'
    active_frame = next(f for f in result1['workflow_stack'] if f['status'] == 'active')
    assert active_frame['awaiting'] == 'vehicle_no'

    # Turn 2: user provides vehicle number
    state2 = store.state_for(record['session_id'])
    state2.update({'session_id': record['session_id'],
                   'messages': list(result1['messages']) + [HumanMessage(content='HR85G2799', id='test-user-2')],
                   'last_user_message': 'HR85G2799', 'response': '', 'sources': [], 'target_frame_id': None,
                   'pending_intents': []})
    result2 = graph.invoke(state2, config={'configurable': {'thread_id': record['session_id']}})
    assert result2['vehicle_no'] == 'HR85G2799'

