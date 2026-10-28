from pathlib import Path
from unittest.mock import MagicMock
import pytest

from trackobit_assistant.services.module_taxonomy import ModuleTaxonomyService
from trackobit_assistant.schemas.models import ModuleClassification
from trackobit_assistant.adapters.pinecone_bug_store import PineconeBugStore
from trackobit_assistant.nodes.intent.module_disambiguator import make_node as make_disambiguator_node


def test_taxonomy_service_loads_config():
    service = ModuleTaxonomyService(Path("config/application_modules.yaml"))
    modules = service.get_modules()
    assert "reports" in modules
    assert "live_tracking" in modules
    assert "playback" in modules
    assert "maintenance" in modules
    assert "alerts" in modules


def test_heuristic_classify_explicit_and_ambiguous():
    service = ModuleTaxonomyService(Path("config/application_modules.yaml"))

    # Explicit mention of reports
    res_explicit = service._heuristic_classify("in distance report distance is shown in miles")
    assert res_explicit.detected_module == "reports"
    assert not res_explicit.is_ambiguous

    # Ambiguous query matching distance concept across multiple modules
    res_ambiguous = service._heuristic_classify("distance is more than it should actually be")
    assert res_ambiguous.is_ambiguous
    assert res_ambiguous.detected_module is None
    assert len(res_ambiguous.candidate_modules) > 1
    assert "reports" in res_ambiguous.candidate_modules
    assert "live_tracking" in res_ambiguous.candidate_modules

    # Unrelated general text
    res_general = service._heuristic_classify("hello good morning")
    assert not res_general.is_ambiguous
    assert res_general.detected_module is None


def test_disambiguation_message_and_resolution():
    service = ModuleTaxonomyService(Path("config/application_modules.yaml"))
    candidates = ["reports", "live_tracking", "playback"]
    prompt = service.build_disambiguation_message(candidates)

    assert "1." in prompt
    assert "Distance / Travel Reports" in prompt or "Distance & Travel Reports" in prompt
    assert "2." in prompt
    assert "Live Tracking" in prompt

    # Resolve by number
    assert service.resolve_user_choice("1", candidates) == "reports"
    assert service.resolve_user_choice("option 2", candidates) == "live_tracking"
    assert service.resolve_user_choice("3", candidates) == "playback"

    # Resolve by name/keyword
    assert service.resolve_user_choice("reports", candidates) == "reports"
    assert service.resolve_user_choice("in live tracking dashboard", candidates) == "live_tracking"

    # Invalid choice
    assert service.resolve_user_choice("99", candidates) is None
    assert service.resolve_user_choice("something else completely", candidates) is None


def test_module_disambiguator_node_prompts_when_ambiguous():
    service = ModuleTaxonomyService(Path("config/application_modules.yaml"))
    mock_runtime = MagicMock()
    mock_runtime.module_taxonomy = service
    mock_runtime.llm = None  # test deterministic heuristic path

    node = make_disambiguator_node(mock_runtime)

    state = {
        "session_id": "test-sess",
        "last_user_message": "distance is more than it should actually be",
        "awaiting": "none",
    }
    result = node(state)

    assert result.get("awaiting") == "module_choice"
    assert len(result.get("candidate_modules", [])) > 1
    assert "To help you with this issue, could you specify which section" in result.get("response", "")
    assert result.get("pending_module_query") == "distance is more than it should actually be"


def test_module_disambiguator_node_resolves_choice():
    service = ModuleTaxonomyService(Path("config/application_modules.yaml"))
    mock_runtime = MagicMock()
    mock_runtime.module_taxonomy = service

    node = make_disambiguator_node(mock_runtime)

    state = {
        "session_id": "test-sess",
        "last_user_message": "1",
        "awaiting": "module_choice",
        "candidate_modules": ["reports", "live_tracking"],
        "pending_module_query": "distance is more than it should actually be",
    }
    result = node(state)

    assert result.get("selected_module") == "reports"
    assert result.get("awaiting") == "none"
    assert result.get("candidate_modules") == []
    # Restored original query
    assert result.get("last_user_message") == "distance is more than it should actually be"
    assert result.get("pending_module_query") is None


def test_pinecone_bug_store_module_filtering():
    mock_vector_store = MagicMock()
    mock_embeddings = MagicMock()

    store = PineconeBugStore(index_name="test-bugs", api_key="fake-key", embeddings=mock_embeddings)
    store._vector_store = mock_vector_store

    from langchain_core.documents import Document

    doc_reports = Document(
        page_content="Distance shown in miles: reports distance error",
        metadata={
            "bug_id": "BUG-01",
            "title": "Distance in miles",
            "symptoms": "distance shown in miles",
            "module": "reports",
            "status": "active",
        }
    )
    doc_tracking = Document(
        page_content="Live map odometer lagging",
        metadata={
            "bug_id": "BUG-02",
            "title": "Live Map Lag",
            "symptoms": "live tracking delay",
            "module": "live_tracking",
            "status": "active",
        }
    )

    # Both returned by vector similarity
    mock_vector_store.similarity_search_with_score.return_value = [
        (doc_reports, 0.88),
        (doc_tracking, 0.70),
    ]

    # When querying for reports module, BUG-01 matches
    res_reports = store.search_active_bug("distance issue", min_similarity=0.65, module="reports")
    assert res_reports is not None
    assert res_reports["bug_id"] == "BUG-01"

    # When querying for live_tracking module, BUG-01 is filtered out and BUG-02 matches
    res_tracking = store.search_active_bug("distance issue", min_similarity=0.65, module="live_tracking")
    assert res_tracking is not None
    assert res_tracking["bug_id"] == "BUG-02"

    # When querying for maintenance module, neither matches -> returns None
    res_maint = store.search_active_bug("distance issue", min_similarity=0.65, module="maintenance")
    assert res_maint is None


def test_symptom_analyzer_deflects_bug_even_when_session_had_vehicle():
    from trackobit_assistant.nodes.intake.symptom_analyzer import make_node as make_symptom_node

    mock_bug_store = MagicMock()
    mock_bug_store.search_active_bug.return_value = {
        "bug_id": "Bug-01",
        "title": "in distance report distance is shown in miles",
        "workaround": "use trackobit mobile app for now",
        "eta": "2 weeks from now",
        "module": "reports",
    }

    mock_runtime = MagicMock()
    mock_runtime.bug_store = mock_bug_store
    mock_runtime.llm = None
    mock_runtime.prompts = None

    node = make_symptom_node(mock_runtime)

    # State where vehicle was present from previous turn in the session
    state = {
        "session_id": "test-sess",
        "last_user_message": "i am getting issue with distance on my application",
        "selected_module": "reports",
        "vehicle_no": "HR85G2799",
        "workflow_stack": [],
    }

    result = node(state)
    assert result.get("resolved") is True
    assert result.get("fault_category") == "known_software_outage"
    assert "Bug-01" in result.get("response", "")
    assert "use trackobit mobile app for now" in result.get("response", "")


def test_check_config_does_not_treat_wrong_distance_as_port_rejection():
    from trackobit_assistant.nodes.troubleshooting.check_config import make_node as make_check_config_node

    mock_runtime = MagicMock()
    mock_runtime.bug_store = None
    mock_runtime.llm = None

    node = make_check_config_node(mock_runtime)

    # User says "i have wrong distance in distance report" while awaiting port confirmation
    state = {
        "session_id": "test-sess",
        "last_user_message": "i have wrong distance in distance report",
        "awaiting": "config_port_confirm",
        "vehicle_no": "HR85G2799",
        "vehicle_snapshot": {"port": 8503},
    }

    result = node(state)
    # Must NOT reject the port or escalate to human handoff!
    assert result.get("current_step") != "human_handoff"
    assert result.get("handoff_reason") is None
    # Instead, re-prompts for confirmation
    assert "Please confirm with 'yes' or 'no'" in result.get("response", "")
