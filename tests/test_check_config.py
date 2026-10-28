"""Tests for vehicle device configuration validation node (check_config)."""
import pytest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from langchain_core.messages import HumanMessage

from trackobit_assistant.adapters.command_registry import YamlCommandRegistry
from trackobit_assistant.adapters.knowledge_base import FileKnowledgeBase
from trackobit_assistant.adapters.session_store_memory import MemorySessionStore
from trackobit_assistant.adapters.ticket_client import LoggingTicketClient
from trackobit_assistant.config.settings import Settings
from trackobit_assistant.graph.builder import build_graph
from trackobit_assistant.graph.runtime import Runtime
from trackobit_assistant.nodes.troubleshooting.check_config import make_node as make_check_config_node
from trackobit_assistant.adapters.vehicle_api import VehicleNotFoundError
from trackobit_assistant.schemas.models import ValidationStatus, VehicleSnapshot
from trackobit_assistant.services.prompt_repository import PromptRepository


class FakeVehicleApiClient:
    def __init__(self, snapshot: VehicleSnapshot | None = None):
        self.snapshot = snapshot

    def get_vehicle(self, vehicle_no: str) -> VehicleSnapshot:
        if str(vehicle_no).upper() in ('NOTFOUND', 'HR85G2790', 'INVALID'):
            raise VehicleNotFoundError(f"Vehicle '{vehicle_no}' does not exist or is not active in the system.")
        if self.snapshot is not None:
            return self.snapshot
        return VehicleSnapshot(
            vehicle_no=vehicle_no,
            state="unreachable",
            device_type="Concox V5",
            port=5023,
            vehicle_status="Active",
            device_status="Active",
            minutes_since_last_update=15.0,
            last_update=datetime.now(timezone.utc),
            since=datetime.now(timezone.utc),
            hours_since_status=1.0,
            imei="355172108792241",
        )


def _create_test_runtime(tmp_path: Path, vehicle_client=None):
    kb_dir = tmp_path / "kb"
    kb_dir.mkdir(parents=True, exist_ok=True)
    # Populate approved RAG files
    (kb_dir / "device_activation.md").write_text(
        "# Device Activation\nNavigate to Vehicle Management and toggle Device Status to Active.",
        encoding="utf-8"
    )
    (kb_dir / "subscription_renewal.md").write_text(
        "# Subscription Renewal\nNavigate to Billing and complete the renewal payment.",
        encoding="utf-8"
    )

    settings = Settings(
        data_dir=tmp_path,
        session_dir=tmp_path / "sessions",
        upload_dir=tmp_path / "uploads",
        knowledge_dir=kb_dir,
        commands_dir=Path(__file__).parents[1] / "data" / "commands",
    )
    settings.ensure_directories()
    store = MemorySessionStore()
    runtime = Runtime(
        settings=settings,
        session_store=store,
        vehicle_client=vehicle_client or FakeVehicleApiClient(),
        ticket_client=LoggingTicketClient(),
        command_registry=YamlCommandRegistry(settings.commands_dir),
        knowledge_base=FileKnowledgeBase(kb_dir),
        llm=None,
        vision_llm=None,
        prompts=PromptRepository(Path(__file__).parents[1] / "prompts"),
    )
    return runtime, store


# ---------------------------------------------------------------------------
# Unit tests for check_config node
# ---------------------------------------------------------------------------

def test_missing_port_escalates_to_human_handoff(tmp_path: Path):
    runtime, _ = _create_test_runtime(tmp_path)
    node = make_check_config_node(runtime)
    state = {
        "vehicle_no": "HR85G2799",
        "vehicle_snapshot": {
            "vehicle_no": "HR85G2799",
            "state": "unreachable",
            "device_type": "Concox V5",
            "port": None,  # Missing port
            "vehicle_status": "Active",
            "device_status": "Active",
            "minutes_since_last_update": 15.0,
        },
        "config_device_type_status": ValidationStatus.VALID.value,
        "awaiting": "none",
    }
    result = node(state)
    assert result["current_step"] == "human_handoff"
    assert result["handoff_reason"] == "missing_configured_port"
    assert result["config_port_status"] == ValidationStatus.INVALID.value


def test_missing_device_type_escalates(tmp_path: Path):
    runtime, _ = _create_test_runtime(tmp_path)
    node = make_check_config_node(runtime)
    state = {
        "vehicle_no": "HR85G2799",
        "vehicle_snapshot": {
            "vehicle_no": "HR85G2799",
            "state": "unreachable",
            "device_type": "",  # Missing device type
            "port": 5023,
            "vehicle_status": "Active",
            "device_status": "Active",
            "minutes_since_last_update": 15.0,
        },
        "awaiting": "none",
    }
    result = node(state)
    assert result["current_step"] == "human_handoff"
    assert result["handoff_reason"] == "missing_device_type"


def test_non_unreachable_bypasses_port_and_device_checks(tmp_path: Path):
    runtime, _ = _create_test_runtime(tmp_path)
    node = make_check_config_node(runtime)

    # Device is Idle and fresh (minutes=2.0)
    snapshot_idle = {
        "vehicle_no": "HR85G2799",
        "state": "Idle",
        "device_type": "Concox V5",
        "port": 8503,  # Even if mismatched, should bypass because state != unreachable
        "vehicle_status": "Active",
        "device_status": "Active",
        "minutes_since_last_update": 2.0,
    }
    res_idle = node({"vehicle_no": "HR85G2799", "vehicle_snapshot": snapshot_idle, "awaiting": "none"})
    assert res_idle["config_port_status"] == ValidationStatus.VALID.value
    assert res_idle["config_device_type_status"] == ValidationStatus.VALID.value
    assert res_idle["awaiting"] == "none"


def test_unreachable_lu_under_10m_acknowledges_device_type_only(tmp_path: Path):
    runtime, _ = _create_test_runtime(tmp_path)
    node = make_check_config_node(runtime)

    # Device is unreachable but lu is smaller than 10 min (4.0 mins)
    snapshot_fresh_unreachable = {
        "vehicle_no": "HR85G2799",
        "state": "unreachable",
        "device_type": "Concox V5",
        "port": 8503,  # Mismatched port in system records
        "vehicle_status": "Active",
        "device_status": "Active",
        "minutes_since_last_update": 4.0,
    }

    # Turn 1: Acknowledges device type only (asks to confirm device model, not port)
    res1 = node({"vehicle_no": "HR85G2799", "vehicle_snapshot": snapshot_fresh_unreachable, "awaiting": "none"})
    assert res1["awaiting"] == "config_device_type_confirm"
    assert "Concox V5" in res1["response"]
    assert "8503" not in res1["response"]  # Does not ask about port!

    # Turn 2: User confirms device type -> port check is bypassed because lu < 10m
    res2 = node({
        "vehicle_no": "HR85G2799",
        "vehicle_snapshot": snapshot_fresh_unreachable,
        "awaiting": "config_device_type_confirm",
        "last_user_message": "yes, correct",
    })
    assert res2["config_device_type_status"] == ValidationStatus.VALID.value
    assert res2["config_port_status"] == ValidationStatus.VALID.value
    # Does not ask for port confirmation or port fix
    assert res2.get("awaiting") == "none"


def test_unreachable_stale_device_type_rejected_escalates(tmp_path: Path):
    runtime, _ = _create_test_runtime(tmp_path)
    node = make_check_config_node(runtime)
    snapshot = {
        "vehicle_no": "HR85G2799",
        "state": "unreachable",
        "device_type": "Concox V5",
        "port": 5023,
        "vehicle_status": "Active",
        "device_status": "Active",
        "minutes_since_last_update": 15.0,
    }

    # Turn 1: Bot asks for device model confirmation
    state1 = {"vehicle_no": "HR85G2799", "vehicle_snapshot": snapshot, "awaiting": "none"}
    res1 = node(state1)
    assert res1["awaiting"] == "config_device_type_confirm"
    assert "Concox V5" in res1["response"]

    # Turn 2: User rejects device model -> escalates to support
    state2 = {
        "vehicle_no": "HR85G2799",
        "vehicle_snapshot": snapshot,
        "awaiting": "config_device_type_confirm",
        "last_user_message": "no, my device is Teltonika",
    }
    res2 = node(state2)
    assert res2["current_step"] == "human_handoff"
    assert res2["handoff_reason"] == "incorrect_device_type_reconfiguration_required"


def test_unreachable_stale_port_mismatch_instructs_user_to_fix(tmp_path: Path):
    runtime, _ = _create_test_runtime(tmp_path)
    node = make_check_config_node(runtime)
    # Master registry for Concox V5 expects port 5023, but vehicle has 8503
    snapshot = {
        "vehicle_no": "HR85G2799",
        "state": "unreachable",
        "device_type": "Concox V5",
        "port": 8503,
        "vehicle_status": "Active",
        "device_status": "Active",
        "minutes_since_last_update": 15.0,
    }

    # Turn 1: Asks to confirm device type
    state1 = {"vehicle_no": "HR85G2799", "vehicle_snapshot": snapshot, "awaiting": "none"}
    res1 = node(state1)
    assert res1["awaiting"] == "config_device_type_confirm"

    # Turn 2: Client confirms device type -> bot identifies port mismatch (8503 vs 5023)
    state2 = {
        "vehicle_no": "HR85G2799",
        "vehicle_snapshot": snapshot,
        "awaiting": "config_device_type_confirm",
        "last_user_message": "yes, it is Concox V5",
    }
    res2 = node(state2)
    assert res2["awaiting"] == "config_port_fix_confirm"
    assert "8503" in res2["response"]
    assert "5023" in res2["response"]
    assert "SERVER,0,52.74.44.145,5023,0#" in res2["response"]
    assert "Please fix the port configuration" in res2["response"]

    # Turn 3: User confirms they fixed the port -> proceeds to valid port status
    state3 = {
        "vehicle_no": "HR85G2799",
        "vehicle_snapshot": snapshot,
        "awaiting": "config_port_fix_confirm",
        "last_user_message": "done, I have updated the port",
        "config_device_type_status": ValidationStatus.VALID.value,
    }
    res3 = node(state3)
    assert res3["config_port_status"] == ValidationStatus.VALID.value


def test_unreachable_stale_port_matching_flow(tmp_path: Path):
    runtime, _ = _create_test_runtime(tmp_path)
    node = make_check_config_node(runtime)
    # Port 5023 matches master registry for Concox V5
    snapshot = {
        "vehicle_no": "HR85G2799",
        "state": "unreachable",
        "device_type": "Concox V5",
        "port": 5023,
        "vehicle_status": "Active",
        "device_status": "Active",
        "minutes_since_last_update": 15.0,
    }

    # Turn 1: Device type confirmation
    state1 = {"vehicle_no": "HR85G2799", "vehicle_snapshot": snapshot, "awaiting": "none"}
    res1 = node(state1)
    assert res1["awaiting"] == "config_device_type_confirm"

    # Turn 2: User confirms device type -> bot asks port confirmation
    state2 = {
        "vehicle_no": "HR85G2799",
        "vehicle_snapshot": snapshot,
        "awaiting": "config_device_type_confirm",
        "last_user_message": "yes",
    }
    res2 = node(state2)
    assert res2["awaiting"] == "config_port_confirm"
    assert "port 5023" in res2["response"]

    # Turn 3: User confirms port -> port marked valid
    state3 = {
        "vehicle_no": "HR85G2799",
        "vehicle_snapshot": snapshot,
        "awaiting": "config_port_confirm",
        "last_user_message": "yes, correct",
        "config_device_type_status": ValidationStatus.VALID.value,
    }
    res3 = node(state3)
    assert res3["config_port_status"] == ValidationStatus.VALID.value


def test_inactive_vehicle_with_expired_subscription_uses_rag(tmp_path: Path):
    runtime, _ = _create_test_runtime(tmp_path)
    node = make_check_config_node(runtime)
    past_date = (datetime.now() - timedelta(days=10)).isoformat()
    snapshot = {
        "vehicle_no": "HR85G2799",
        "device_type": "Concox V5",
        "port": 8503,
        "vehicle_status": "Inactive",
        "device_status": "Active",
        "subscription_due": past_date,
    }
    state = {
        "vehicle_no": "HR85G2799",
        "vehicle_snapshot": snapshot,
        "config_port_status": ValidationStatus.VALID.value,
        "config_device_type_status": ValidationStatus.VALID.value,
        "awaiting": "none",
    }
    res = node(state)
    assert res["awaiting"] == "subscription_renewal_confirm"
    assert "subscription for vehicle HR85G2799 has expired" in res["response"]
    assert "Billing" in res["response"]  # Retrieved from RAG subscription_renewal.md


def test_inactive_vehicle_unexplained_escalates(tmp_path: Path):
    runtime, _ = _create_test_runtime(tmp_path)
    node = make_check_config_node(runtime)
    future_date = (datetime.now() + timedelta(days=100)).isoformat()
    snapshot = {
        "vehicle_no": "HR85G2799",
        "device_type": "Concox V5",
        "port": 8503,
        "vehicle_status": "Inactive",
        "device_status": "Active",
        "subscription_due": future_date,  # Not expired!
    }
    state = {
        "vehicle_no": "HR85G2799",
        "vehicle_snapshot": snapshot,
        "config_port_status": ValidationStatus.VALID.value,
        "config_device_type_status": ValidationStatus.VALID.value,
        "awaiting": "none",
    }
    res = node(state)
    assert res["current_step"] == "human_handoff"
    assert res["handoff_reason"] == "vehicle_inactive_unexplained"


def test_inactive_device_guides_activation_and_revalidates_api(tmp_path: Path):
    # Setup client that still reports inactive when re-queried
    snap_inactive = VehicleSnapshot(
        vehicle_no="HR85G2799",
        device_type="Concox V5",
        port=8503,
        vehicle_status="Active",
        device_status="Inactive",
    )
    runtime, _ = _create_test_runtime(tmp_path, vehicle_client=FakeVehicleApiClient(snap_inactive))
    node = make_check_config_node(runtime)

    # Initial detection: prompt activation
    state1 = {
        "vehicle_no": "HR85G2799",
        "vehicle_snapshot": snap_inactive.model_dump(mode="json"),
        "config_port_status": ValidationStatus.VALID.value,
        "config_device_type_status": ValidationStatus.VALID.value,
        "awaiting": "none",
    }
    res1 = node(state1)
    assert res1["awaiting"] == "device_activation_confirm"
    assert "Device Activation" in res1["response"] or "Vehicle Management" in res1["response"]

    # Client claims "done", but API re-fetch shows device still Inactive -> does NOT accept blindly!
    state2 = {
        "vehicle_no": "HR85G2799",
        "vehicle_snapshot": snap_inactive.model_dump(mode="json"),
        "config_port_status": ValidationStatus.VALID.value,
        "config_device_type_status": ValidationStatus.VALID.value,
        "awaiting": "device_activation_confirm",
        "last_user_message": "done I activated it",
    }
    res2 = node(state2)
    assert res2["current_step"] == "human_handoff"
    assert res2["handoff_reason"] == "device_activation_failed"


def test_fresh_lu_bypasses_stale_diagnostics(tmp_path: Path):
    runtime, _ = _create_test_runtime(tmp_path)
    node = make_check_config_node(runtime)
    snapshot = {
        "vehicle_no": "HR85G2799",
        "device_type": "Concox V5",
        "port": 8503,
        "vehicle_status": "Active",
        "device_status": "Active",
        "minutes_since_last_update": 3.5,  # <= 5.0 mins: FRESH
        "hours_since_status": 2.0,
    }
    state = {
        "vehicle_no": "HR85G2799",
        "vehicle_snapshot": snapshot,
        "config_port_status": ValidationStatus.VALID.value,
        "config_device_type_status": ValidationStatus.VALID.value,
        "awaiting": "none",
    }
    res = node(state)
    # Must route directly to fault_classifier without stale diagnostics or movement requests
    assert res["current_step"] == "fault_classifier"
    assert res["lu_status"] == ValidationStatus.VALID.value
    assert res["awaiting"] == "none"
    assert "stale_diagnostics" not in res


def test_stale_lu_runs_diagnostics_and_safely_escalates_when_unavailable(tmp_path: Path):
    runtime, _ = _create_test_runtime(tmp_path)
    node = make_check_config_node(runtime)
    snapshot = {
        "vehicle_no": "HR85G2799",
        "device_type": "Concox V5",
        "port": 8503,
        "vehicle_status": "Active",
        "device_status": "Active",
        "minutes_since_last_update": 45.0,  # > 5.0 mins: STALE
        "imei": "355172108792241",
    }
    state = {
        "vehicle_no": "HR85G2799",
        "vehicle_snapshot": snapshot,
        "config_port_status": ValidationStatus.VALID.value,
        "config_device_type_status": ValidationStatus.VALID.value,
        "awaiting": "none",
    }
    res = node(state)
    assert res["current_step"] == "human_handoff"
    assert res["handoff_reason"] == "stale_packets_diagnostics_unavailable"
    assert "stale_diagnostics" in res
    assert res["stale_diagnostics"]["check_ip"]["status"] == ValidationStatus.UNAVAILABLE.value
    assert res["stale_diagnostics"]["check_port"]["status"] == ValidationStatus.UNAVAILABLE.value
    assert res["stale_diagnostics"]["check_imei"]["status"] == ValidationStatus.UNAVAILABLE.value


# ---------------------------------------------------------------------------
# Integration tests through LangGraph build_graph
# ---------------------------------------------------------------------------

def test_full_graph_check_config_preserves_symptom_context(tmp_path: Path):
    snap_fresh = VehicleSnapshot(
        vehicle_no="HR85G2799",
        state="unreachable",
        device_type="Concox V5",
        port=5023,
        vehicle_status="Active",
        device_status="Active",
        minutes_since_last_update=15.0,
        last_update=datetime.now(timezone.utc),
        since=datetime.now(timezone.utc),
        hours_since_status=0.5,
    )
    runtime, store = _create_test_runtime(tmp_path, vehicle_client=FakeVehicleApiClient(snap_fresh))
    graph = build_graph(runtime)
    record = store.create_session()

    # Turn 1: user reports location issue with specific AC symptom
    state1 = store.state_for(record["session_id"])
    state1.update({
        "session_id": record["session_id"],
        "messages": [HumanMessage(content="My car HR85G2799 AC is not working and location is strange", id="m1")],
        "last_user_message": "My car HR85G2799 AC is not working and location is strange",
        "response": "",
        "sources": [],
        "target_frame_id": None,
        "pending_intents": [],
    })
    result1 = graph.invoke(state1, config={"configurable": {"thread_id": record["session_id"]}})
    store.save_graph_result(record["session_id"], result1)

    # Reaches check_config and asks for device type confirmation
    assert result1["awaiting"] == "config_device_type_confirm"
    assert "Concox V5" in result1["response"]
    # Verify symptom context is preserved
    assert "AC" in result1["symptoms"]["summary"] or "AC" in result1["symptoms"]["raw_user_message"]

    # Turn 2: Confirm device type
    state2 = store.state_for(record["session_id"])
    state2.update({
        "session_id": record["session_id"],
        "messages": list(result1["messages"]) + [HumanMessage(content="yes that is my device", id="m2")],
        "last_user_message": "yes that is my device",
        "response": "",
        "sources": [],
        "target_frame_id": None,
        "pending_intents": [],
    })
    result2 = graph.invoke(state2, config={"configurable": {"thread_id": record["session_id"]}})
    store.save_graph_result(record["session_id"], result2)

    # Next check: asks for port confirmation
    assert result2["awaiting"] == "config_port_confirm"
    assert "5023" in result2["response"]

    # Turn 3: Confirm port
    state3 = store.state_for(record["session_id"])
    state3.update({
        "session_id": record["session_id"],
        "messages": list(result2["messages"]) + [HumanMessage(content="yes, port is correct", id="m3")],
        "last_user_message": "yes, port is correct",
        "response": "",
        "sources": [],
        "target_frame_id": None,
        "pending_intents": [],
    })
    result3 = graph.invoke(state3, config={"configurable": {"thread_id": record["session_id"]}})
    store.save_graph_result(record["session_id"], result3)

    assert result3["config_port_status"] == ValidationStatus.VALID.value
    assert result3["config_device_type_status"] == ValidationStatus.VALID.value


@pytest.mark.parametrize("query", [
    "i wanna check the configuration for my vehicle number HR85G2799",
    "which device is connected with vehicle HR85G2799",
    "tell me details of vehicle HR85G2799",
    "hit api to get vehicle details of this vehicle HR85G2799",
])
def test_vehicle_queries_reach_check_config_node(tmp_path: Path, query: str):
    snap = VehicleSnapshot(
        vehicle_no="HR85G2799",
        state="unreachable",
        device_type="Concox V5",
        port=5023,
        vehicle_status="Active",
        device_status="Active",
        minutes_since_last_update=15.0,
        last_update=datetime.now(timezone.utc),
        since=datetime.now(timezone.utc),
        hours_since_status=1.0,
        imei="355172108792241",
    )
    runtime, store = _create_test_runtime(tmp_path, vehicle_client=FakeVehicleApiClient(snap))
    graph = build_graph(runtime)
    record = store.create_session()

    state = store.state_for(record["session_id"])
    state.update({
        "session_id": record["session_id"],
        "messages": [HumanMessage(content=query, id="m1")],
        "last_user_message": query,
        "response": "",
        "sources": [],
        "target_frame_id": None,
        "pending_intents": [],
    })
    result = graph.invoke(state, config={"configurable": {"thread_id": record["session_id"]}})

    # Must NOT route to show_device_commands or rag_answer
    assert "Please specify the device type you would like commands for" not in result["response"]
    assert "The current knowledge base does not contain an approved answer" not in result["response"]
    # Must reach check_config and ask about device type confirmation
    assert result["awaiting"] == "config_device_type_confirm"
    assert "Concox V5" in result["response"]


def test_check_config_completion_summarizes_when_no_issue(tmp_path: Path):
    snap = VehicleSnapshot(
        vehicle_no="HR85G2799",
        state="Idle",
        device_type="Concox V5",
        port=5023,
        vehicle_status="Active",
        device_status="Active",
        minutes_since_last_update=2.0,
        last_update=datetime.now(timezone.utc),
        since=datetime.now(timezone.utc),
        hours_since_status=1.0,
        imei="355172108792241",
        satellites=15,
        gsm_signals=4,
        battery=100.0,
    )
    runtime, store = _create_test_runtime(tmp_path, vehicle_client=FakeVehicleApiClient(snap))
    graph = build_graph(runtime)
    record = store.create_session()

    # Turn 1: user asks to check configuration for an active, fresh vehicle
    state1 = store.state_for(record["session_id"])
    state1.update({
        "session_id": record["session_id"],
        "messages": [HumanMessage(content="i wanna check the configuration for my vehicle HR85G2799", id="m1")],
        "last_user_message": "i wanna check the configuration for my vehicle HR85G2799",
        "response": "",
        "sources": [],
        "target_frame_id": None,
        "pending_intents": [],
    })
    result1 = graph.invoke(state1, config={"configurable": {"thread_id": record["session_id"]}})
    store.save_graph_result(record["session_id"], result1)

    # Must NOT ask "Is the tracking issue resolved now?"
    assert "Is the tracking issue resolved now" not in result1["response"]
    # Must report configuration & status summary confirming everything looks fine
    assert "Configuration & Status Summary" in result1["response"]
    assert "Everything looks fine" in result1["response"] or "working properly" in result1["response"]
    assert "5023" in result1["response"]
    assert "Concox V5" in result1["response"]
    assert result1["awaiting"] == "none"


def test_switching_vehicle_number_during_active_workflow(tmp_path: Path):
    runtime, store = _create_test_runtime(tmp_path)
    graph = build_graph(runtime)
    record = store.create_session()

    # Turn 1: user reports location issue for vehicle HR85G2799
    state1 = store.state_for(record["session_id"])
    state1.update({
        "session_id": record["session_id"],
        "messages": [HumanMessage(content="location not updating for HR85G2799", id="m1")],
        "last_user_message": "location not updating for HR85G2799",
        "response": "",
        "sources": [],
        "target_frame_id": None,
        "pending_intents": [],
    })
    result1 = graph.invoke(state1, config={"configurable": {"thread_id": record["session_id"]}})
    store.save_graph_result(record["session_id"], result1)

    assert result1["vehicle_no"] == "HR85G2799"
    assert result1["awaiting"] == "config_device_type_confirm"

    # Turn 2: user says they are asking about another vehicle HR85G2791
    state2 = store.state_for(record["session_id"])
    state2.update({
        "session_id": record["session_id"],
        "messages": list(result1["messages"]) + [HumanMessage(content="i am asking about another vehicle number that is HR85G2791", id="m2")],
        "last_user_message": "i am asking about another vehicle number that is HR85G2791",
        "response": "",
        "sources": [],
        "target_frame_id": None,
        "pending_intents": [],
    })
    result2 = graph.invoke(state2, config={"configurable": {"thread_id": record["session_id"]}})
    store.save_graph_result(record["session_id"], result2)

    # Must switch to HR85G2791, pausing HR85G2799 on stack
    assert result2["vehicle_no"] == "HR85G2791"
    # First vehicle HR85G2799 must be paused on the workflow stack
    stack = result2.get("workflow_stack") or []
    assert any(f.get("status") == "paused" and f.get("context", {}).get("vehicle_no") == "HR85G2799" for f in stack)


def test_vehicle_does_not_exist_informs_user_and_does_not_escalate(tmp_path: Path):
    runtime, store = _create_test_runtime(tmp_path)
    graph = build_graph(runtime)
    record = store.create_session()

    state = store.state_for(record["session_id"])
    state.update({
        "session_id": record["session_id"],
        "messages": [HumanMessage(content="location not updating for HR85G2790", id="m1")],
        "last_user_message": "location not updating for HR85G2790",
        "response": "",
        "sources": [],
        "target_frame_id": None,
        "pending_intents": [],
    })
    result = graph.invoke(state, config={"configurable": {"thread_id": record["session_id"]}})

    # Must NOT escalate to human_handoff or create a ticket
    assert result.get("handoff_reason") is None
    assert result.get("ticket_info") is None
    assert result.get("current_step") != "human_handoff"
    # Must inform the user that vehicle does not exist or is not active
    assert "does not exist" in result["response"] or "not active" in result["response"]
    assert "HR85G2790" in result["response"]
    # Must await a valid vehicle number
    assert result["awaiting"] == "vehicle_no"



def test_colloquial_affirmation_and_negative_in_config(tmp_path: Path):
    from trackobit_assistant.nodes.troubleshooting.check_config import _is_affirmative, _is_negative

    # Affirmative variations
    assert _is_affirmative("yes")
    assert _is_affirmative("yea")
    assert _is_affirmative("yeahhhhhh")
    assert _is_affirmative("yeaaah")
    assert _is_affirmative("yeee")
    assert _is_affirmative("yup")
    assert _is_affirmative("yep")
    assert _is_affirmative("haan")

    # Negative variations
    assert _is_negative("no")
    assert _is_negative("nah")
    assert _is_negative("nahhhh")
    assert _is_negative("nope")
    assert _is_negative("nahi")


def test_buffering_issue_does_not_falsely_resolve(tmp_path: Path):
    snap = VehicleSnapshot(
        vehicle_no="HR85G2799",
        state="Idle",
        device_type="Concox V5",
        port=5023,
        vehicle_status="Active",
        device_status="Active",
        minutes_since_last_update=2.0,
        last_update=datetime.now(timezone.utc),
        since=datetime.now(timezone.utc),
        hours_since_status=1.0,
        imei="355172108792241",
    )
    runtime, store = _create_test_runtime(tmp_path, vehicle_client=FakeVehicleApiClient(snap))
    graph = build_graph(runtime)
    record = store.create_session()

    # Turn 1: user reports buffering for vehicle
    state1 = store.state_for(record["session_id"])
    state1.update({
        "session_id": record["session_id"],
        "messages": [HumanMessage(content="device is buffering for vehicle HR85G2799", id="m1")],
        "last_user_message": "device is buffering for vehicle HR85G2799",
        "response": "",
        "sources": [],
        "target_frame_id": None,
        "pending_intents": [],
    })
    result1 = graph.invoke(state1, config={"configurable": {"thread_id": record["session_id"]}})

    # Config sanity passed without bothering client, telemetry is fresh (2 mins), but user reported "buffering"
    # It must NOT say "No configuration or tracking faults were detected" or mark resolved=True
    assert not result1.get("resolved")
    assert result1.get("fault_category") == "software_issue"
    assert result1.get("ticket_info") is not None
    assert result1["ticket_info"]["status"] == "created"


def test_colloquial_affirmation_in_unreachable_config_flow(tmp_path: Path):
    runtime, store = _create_test_runtime(tmp_path)
    graph = build_graph(runtime)
    record = store.create_session()

    # Turn 1: user reports location issue for unreachable vehicle
    state1 = store.state_for(record["session_id"])
    state1.update({
        "session_id": record["session_id"],
        "messages": [HumanMessage(content="vehicle HR85G2799 is unreachable", id="m1")],
        "last_user_message": "vehicle HR85G2799 is unreachable",
        "response": "",
        "sources": [],
        "target_frame_id": None,
        "pending_intents": [],
    })
    result1 = graph.invoke(state1, config={"configurable": {"thread_id": record["session_id"]}})
    store.save_graph_result(record["session_id"], result1)

    assert result1["awaiting"] == "config_device_type_confirm"

    # Turn 2: user replies with colloquial 'yeaaah'
    state2 = store.state_for(record["session_id"])
    state2.update({
        "session_id": record["session_id"],
        "messages": list(result1["messages"]) + [HumanMessage(content="yeaaah", id="m2")],
        "last_user_message": "yeaaah",
        "response": "",
        "sources": [],
        "target_frame_id": None,
        "pending_intents": [],
    })
    result2 = graph.invoke(state2, config={"configurable": {"thread_id": record["session_id"]}})
    store.save_graph_result(record["session_id"], result2)

    assert result2["awaiting"] == "config_port_confirm"

    # Turn 3: user replies with colloquial 'yeahhhhhh'
    state3 = store.state_for(record["session_id"])
    state3.update({
        "session_id": record["session_id"],
        "messages": list(result2["messages"]) + [HumanMessage(content="yeahhhhhh", id="m3")],
        "last_user_message": "yeahhhhhh",
        "response": "",
        "sources": [],
        "target_frame_id": None,
        "pending_intents": [],
    })
    result3 = graph.invoke(state3, config={"configurable": {"thread_id": record["session_id"]}})

    assert result3["config_port_status"] == ValidationStatus.VALID.value
    assert result3["config_device_type_status"] == ValidationStatus.VALID.value
