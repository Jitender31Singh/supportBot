from typing import Annotated, Any, TypedDict
from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages

class AssistantState(TypedDict, total=False):
    session_id: str
    messages: Annotated[list[AnyMessage], add_messages]
    intent: str
    intent_confidence: float
    query_kind: str
    query_confidence: float
    query_confidence_threshold: float
    device_type_query: str | None
    active_workflow: str
    awaiting: str
    symptoms: dict[str, Any]
    vehicle_no: str | None
    vehicle_snapshot: dict[str, Any] | None
    snapshot_history: list[dict[str, Any]]
    fault_category: str | None
    fault_evidence: list[str]
    troubleshoot_rounds: int
    max_troubleshoot_rounds: int
    command_history: list[dict[str, Any]]
    current_command: dict[str, Any] | None
    retry_counters: dict[str, int]
    ticket_info: dict[str, Any] | None
    resolved: bool
    last_user_message: str
    response: str
    errors: list[str]
    dashboard_evidence: str | None
    screenshot_path: str | None
    screenshot_retry_count: int
    workflow_stack: list[dict[str, Any]]
    active_frame_id: str | None
    pending_intents: list[dict[str, Any]]
    sources: list[str]
    current_step: str | None
    handoff_reason: str | None
    summary: str
    conversation_summary: str
    summary_message_count: int
    paused_at_step: str | None
    target_frame_id: str | None
    resume_prefix: str | None
    resume_announcement: bool
    rag_confidence: float | None
    rag_confidence_threshold: float
    retry_step: str | None
    retry_message: str | None
    retry_exhausted: bool
    vehicle_no_valid: bool
    api_ok: bool | None
    api_error: str | None
    vehicle_not_found: bool
    fault_confidence: float | None
    fault_needs_user_input: bool
    command_available: bool
    parsed_command_output: dict[str, Any] | None
    command_verdict: str | None
    command_analysis: dict[str, Any] | None
    resume_target: str | None
    paused_active_workflow: bool
    paused_to_resume: str | None
    referenced_paused_frame: str | None
    recheck_requested: bool
    pending_resume_frame_id: str | None
    workflow_choice_valid: bool
    intent_retry_exhausted: bool
    resume_represent_step: bool
    config_port_status: str | None
    config_device_type_status: str | None
    device_activation_status: str | None
    subscription_status: str | None
    lu_status: str | None
    since_status: str | None
    stale_diagnostics: dict[str, Any] | None
    config_step: str | None
