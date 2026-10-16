from unittest.mock import MagicMock
from trackobit_assistant.nodes.resolution.resolution_handler import make_node
from trackobit_assistant.schemas.models import ResolutionResult, ResolutionVerdict


class MockSettings:
    max_input_retries = 2
    query_confidence_threshold = 0.60


class MockRuntime:
    def __init__(self, llm=None, prompts=None):
        self.llm = llm
        self.prompts = prompts
        self.settings = MockSettings()


def test_resolution_handler_with_llm_resolved():
    mock_structured_llm = MagicMock()
    mock_structured_llm.invoke.return_value = ResolutionResult(
        verdict=ResolutionVerdict.RESOLVED,
        confidence=0.95,
        explanation="User confirmed the vehicle is online now"
    )
    mock_llm = MagicMock()
    mock_llm.with_structured_output.return_value = mock_structured_llm

    runtime = MockRuntime(llm=mock_llm)
    node = make_node(runtime)

    state = {
        'session_id': 'sess-1',
        'last_user_message': 'Yes, the map shows live location now!',
        'retry_counters': {'resolution_confirm': 1},
        'messages': []
    }

    result = node(state)

    assert result['resolved'] is True
    assert result['awaiting'] == 'none'
    assert result['current_step'] == 'close_session'
    assert 'resolution_confirm' not in result['retry_counters']
    assert 'marked this support session as resolved' in result['response']


def test_resolution_handler_with_llm_not_resolved():
    mock_structured_llm = MagicMock()
    mock_structured_llm.invoke.return_value = ResolutionResult(
        verdict=ResolutionVerdict.NOT_RESOLVED,
        confidence=0.92,
        explanation="User indicates tracker is still offline"
    )
    mock_llm = MagicMock()
    mock_llm.with_structured_output.return_value = mock_structured_llm

    runtime = MockRuntime(llm=mock_llm)
    node = make_node(runtime)

    state = {
        'session_id': 'sess-1',
        'last_user_message': 'No, location is still stuck in yesterday',
        'retry_counters': {},
        'messages': []
    }

    result = node(state)

    assert result['resolved'] is False
    assert result['awaiting'] == 'none'
    assert result['current_step'] == 'continue_diagnosis'
    assert 'continue with the next diagnostic step' in result['response']


def test_resolution_handler_with_llm_unclear_and_retry_exhausted():
    mock_structured_llm = MagicMock()
    mock_structured_llm.invoke.return_value = ResolutionResult(
        verdict=ResolutionVerdict.UNCLEAR,
        confidence=0.40,
        explanation="Ambiguous statement"
    )
    mock_llm = MagicMock()
    mock_llm.with_structured_output.return_value = mock_structured_llm

    runtime = MockRuntime(llm=mock_llm)
    node = make_node(runtime)

    # Attempt 1
    state = {
        'session_id': 'sess-1',
        'last_user_message': 'I am not sure',
        'retry_counters': {},
        'messages': []
    }
    result1 = node(state)
    assert result1['awaiting'] == 'resolution_confirm'
    assert result1['retry_counters']['resolution_confirm'] == 1
    assert 'Attempt 1 of 2' in result1['response']

    # Attempt 2 -> exhausted
    state2 = {
        'session_id': 'sess-1',
        'last_user_message': 'Maybe tomorrow',
        'retry_counters': result1['retry_counters'],
        'messages': []
    }
    result2 = node(state2)
    assert result2['retry_exhausted'] is True
    assert result2['current_step'] == 'human_handoff'
    assert result2['awaiting'] == 'none'


def test_resolution_handler_fallback_when_llm_fails():
    mock_structured_llm = MagicMock()
    mock_structured_llm.invoke.side_effect = RuntimeError("LLM API error")
    mock_llm = MagicMock()
    mock_llm.with_structured_output.return_value = mock_structured_llm

    runtime = MockRuntime(llm=mock_llm)
    node = make_node(runtime)

    state = {
        'session_id': 'sess-1',
        'last_user_message': 'yes it is working now',
        'retry_counters': {},
        'messages': []
    }

    result = node(state)
    assert result['resolved'] is True
    assert result['current_step'] == 'close_session'
