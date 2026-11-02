import pytest
from pathlib import Path
from trackobit_assistant.config.settings import Settings
from trackobit_assistant.graph.runtime import Runtime
from trackobit_assistant.adapters.command_registry import YamlCommandRegistry
from trackobit_assistant.nodes.intent.query_classifier import make_node
from trackobit_assistant.schemas.models import QueryKind


@pytest.fixture
def classifier_node():
    settings = Settings()
    commands_dir = Path(__file__).parents[1] / "data" / "commands"
    cmd_registry = YamlCommandRegistry(commands_dir)
    runtime = Runtime(
        settings=settings,
        session_store=None,
        vehicle_client=None,
        ticket_client=None,
        command_registry=cmd_registry,
        knowledge_base=None,
        llm=None,  # Tests baseline & guardrail logic deterministically
        vision_llm=None,
        prompts=None,
    )
    return make_node(runtime)


@pytest.mark.parametrize("query", [
    "how do i add a new vehicle",
    "how to add vehicle",
    "how can i create geofence for vehicle",
    "can i export reports for vehicle",
    "what is the pricing plan",
    "how to configure settings",
    "where is the documentation for geofence",
])
def test_static_inquiries_are_not_hijacked_by_vehicle_keywords(classifier_node, query):
    state = {"last_user_message": query}
    result = classifier_node(state)
    assert result["query_kind"] == QueryKind.STATIC_INFO.value


@pytest.mark.parametrize("query", [
    "i wanna check the configuration for my vehicle number HR85G2799",
    "which device is connected with vehicle HR85G2799",
    "tell me details of vehicle HR85G2799",
    "hit api to get vehicle details of this vehicle HR85G2799",
    "my vehicle is not updating location",
    "vehicle HR26DK8337 offline",
    "gps signal not working for vehicle",
    "device with IMEI 355172108792241 stopped sending data",
])
def test_diagnosis_inquiries_correctly_classified(classifier_node, query):
    state = {"last_user_message": query}
    result = classifier_node(state)
    assert result["query_kind"] == QueryKind.DIAGNOSIS.value


@pytest.mark.parametrize("query,expected_device", [
    ("what is the commands for device type concox v5?", "Concox V5"),
    ("commands for teltonika", "Teltonika"),
    ("what is the command for concox", "Concox"),
    ("show commands for Concox GT06F", "Concox GT06F"),
    ("what is the reboot command for vehicle HR85G2799", None),
])
def test_command_inquiries_correctly_classified(classifier_node, query, expected_device):
    state = {"last_user_message": query}
    result = classifier_node(state)
    assert result["query_kind"] == QueryKind.DEVICE_COMMANDS.value
    if expected_device:
        assert result["device_type_query"] == expected_device


def test_recap_query(classifier_node):
    state = {"last_user_message": "what did i ask earlier?"}
    result = classifier_node(state)
    assert result["query_kind"] == QueryKind.RECAP_CONVERSATION.value


def test_general_query_defaults_to_static_info(classifier_node):
    state = {"last_user_message": "Who created TrackoBit?"}
    result = classifier_node(state)
    assert result["query_kind"] == QueryKind.STATIC_INFO.value
