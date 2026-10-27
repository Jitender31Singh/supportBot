import pytest
from unittest.mock import MagicMock, patch
from langchain_core.documents import Document

from trackobit_assistant.adapters.pinecone_bug_store import PineconeBugStore


def test_pinecone_bug_store_add_and_delete_with_mock():
    mock_vector_store = MagicMock()
    mock_embeddings = MagicMock()

    store = PineconeBugStore(index_name="test-bugs", api_key="fake-key", embeddings=mock_embeddings)
    store._vector_store = mock_vector_store

    # Test Add
    bug_id = store.add_bug(
        bug_id="BUG-101",
        title="Map Buffering",
        symptoms="Map does not load markers smoothly",
        workaround="Refresh page",
        eta="1 hour",
    )
    assert bug_id == "BUG-101"
    assert mock_vector_store.add_documents.called
    kwargs = mock_vector_store.add_documents.call_args.kwargs
    assert kwargs["documents"][0].metadata["bug_id"] == "BUG-101"
    assert kwargs.get("ids") == ["BUG-101"]

    # Test Delete
    result = store.delete_bug("BUG-101")
    assert result is True
    mock_vector_store.delete.assert_called_once_with(ids=["BUG-101"])


def test_pinecone_bug_store_search_similarity_threshold():
    mock_vector_store = MagicMock()
    mock_embeddings = MagicMock()

    store = PineconeBugStore(index_name="test-bugs", api_key="fake-key", embeddings=mock_embeddings)
    store._vector_store = mock_vector_store

    matched_doc = Document(
        page_content="Map Buffering",
        metadata={
            "bug_id": "BUG-101",
            "title": "Map Buffering",
            "symptoms": "Map does not load markers smoothly",
            "workaround": "Refresh page",
            "eta": "1 hour",
            "status": "active",
        }
    )

    # 1. Score exceeds threshold -> returns bug details
    mock_vector_store.similarity_search_with_score.return_value = [(matched_doc, 0.85)]
    res = store.search_active_bug("map is lagging", min_similarity=0.75)
    assert res is not None
    assert res["bug_id"] == "BUG-101"
    assert res["similarity_score"] == 0.85

    # 2. Score below threshold -> returns None
    mock_vector_store.similarity_search_with_score.return_value = [(matched_doc, 0.60)]
    res_low = store.search_active_bug("how to change email", min_similarity=0.75)
    assert res_low is None



def test_create_bug_ticket_deflects_with_known_bug():
    from trackobit_assistant.nodes.classification.create_bug_ticket import make_node

    mock_bug_store = MagicMock()
    mock_bug_store.search_active_bug.return_value = {
        "bug_id": "BUG-PORTAL-01",
        "title": "Portal Streaming Delay",
        "workaround": "Use the mobile app temporarily.",
        "eta": "2:00 PM IST",
    }

    mock_runtime = MagicMock()
    mock_runtime.bug_store = mock_bug_store

    node_fn = make_node(mock_runtime)
    state = {
        "session_id": "sess-123",
        "last_user_message": "device is buffering",
        "symptoms": {"summary": "device is buffering"},
        "vehicle_no": "HR85G2799",
    }
    result = node_fn(state)

    assert result.get("resolved") is True
    assert result.get("fault_category") == "known_software_outage"
    assert "BUG-PORTAL-01" in result["response"]
    assert "Use the mobile app temporarily." in result["response"]
    # Does not call ticket_client.create
    assert not mock_runtime.ticket_client.create.called


def test_symptom_analyzer_early_deflects_known_bug_without_vehicle():
    from trackobit_assistant.nodes.intake.symptom_analyzer import make_node

    mock_bug_store = MagicMock()
    mock_bug_store.search_active_bug.return_value = {
        "bug_id": "BUG-PORTAL-01",
        "title": "Web Portal Buffering",
        "workaround": "Check statuspage.",
        "eta": "1 hour",
    }

    mock_runtime = MagicMock()
    mock_runtime.llm = None
    mock_runtime.prompts = None
    mock_runtime.bug_store = mock_bug_store

    node_fn = make_node(mock_runtime)
    state = {
        "session_id": "sess-123",
        "last_user_message": "is web portal buffering today?",
    }
    result = node_fn(state)

    assert result.get("resolved") is True
    assert result.get("vehicle_no") is None
    assert "BUG-PORTAL-01" in result["response"]
    assert "Web Portal Buffering" in result["response"]
