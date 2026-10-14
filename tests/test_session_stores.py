from pathlib import Path
import pytest
from trackobit_assistant.adapters.session_store_memory import MemorySessionStore


def _assert_store_contract(store):
    session = store.create_session()
    sid = session['session_id']
    assert store.get_session(sid) is not None
    assert store.state_for(sid)['session_id'] == sid
    assert store.list_sessions()[0]['session_id'] == sid
    assert store.get_summary(sid) == ''


def test_memory_session_store_basic_contract():
    _assert_store_contract(MemorySessionStore())


def test_json_session_store_basic_contract(tmp_path: Path):
    pytest.importorskip('langchain_core')
    from trackobit_assistant.adapters.session_store_json import JsonSessionStore
    _assert_store_contract(JsonSessionStore(tmp_path))
