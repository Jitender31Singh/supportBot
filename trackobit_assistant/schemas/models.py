from datetime import datetime, timezone
try:
    from enum import StrEnum
except ImportError:
    from enum import Enum

    class StrEnum(str, Enum):  # type: ignore[no-redef]
        pass
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field

class Intent(StrEnum):
    GREETING = 'greeting'
    SMALLTALK = 'smalltalk'
    NEW_QUERY = 'new_query'
    FOLLOW_UP = 'follow_up'
    ANSWERS_PENDING = 'answers_pending'
    RESOLUTION_REPLY = 'resolution_reply'
    SIDE_QUESTION = 'side_question'
    RESUME_REQUEST = 'resume_request'
    NEW_WORKFLOW = 'new_workflow'
    REFERENCES_PAUSED = 'references_paused'
    AMBIGUOUS_TARGET = 'ambiguous_target'
    RECAP_CONVERSATION = 'recap_conversation'
    UNCLEAR = 'unclear'

class IntentItem(BaseModel):
    intent: Intent
    text: str | None = None
    target_frame_id: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)


class IntentResult(BaseModel):
    intent: Intent = Intent.UNCLEAR
    confidence: float = Field(default=0.5, ge=0, le=1)
    is_follow_up: bool = False
    reasoning: str = ''
    target_frame_id: str | None = None
    intents: list[IntentItem] = Field(default_factory=list)

class SymptomsResult(BaseModel):
    summary: str = ''
    vehicle_no: str | None = None
    device_type_mention: str | None = None
    urgency: str = 'normal'
    user_observation: str | None = None

class QueryKind(StrEnum):
    STATIC_INFO = 'static_info'
    DIAGNOSIS = 'diagnosis'
    DEVICE_COMMANDS = 'device_commands'
    RECAP_CONVERSATION = 'recap_conversation'

class QueryClassification(BaseModel):
    kind: QueryKind = QueryKind.DIAGNOSIS
    confidence: float = Field(default=0.5, ge=0, le=1)
    reason: str = ''
    device_type: str | None = None

class ResolutionVerdict(StrEnum):
    RESOLVED = 'resolved'
    NOT_RESOLVED = 'not_resolved'
    UNCLEAR = 'unclear'

class ResolutionResult(BaseModel):
    verdict: ResolutionVerdict = ResolutionVerdict.UNCLEAR
    confidence: float = Field(default=0.5, ge=0, le=1)
    explanation: str = ''

class ValidationStatus(StrEnum):
    VALID = 'valid'
    INVALID = 'invalid'
    UNKNOWN = 'unknown'
    PENDING = 'pending'
    UNAVAILABLE = 'unavailable'
    FAILED = 'failed'

class DiagnosticCheckResult(BaseModel):
    check_name: str
    status: ValidationStatus = ValidationStatus.UNKNOWN
    evidence: list[str] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)
    recommended_action: str | None = None

class FaultCategory(StrEnum):
    ACCOUNT_ISSUE = 'account_issue'
    SOFTWARE_ISSUE = 'software_issue'
    HARDWARE_ISSUE = 'hardware_issue'
    PARKED_IGNITION_OFF = 'parked_ignition_off'
    NO_ISSUE = 'no_issue'
    NEED_MORE_INFO = 'need_more_info'
    UNKNOWN = 'unknown'

class FaultResult(BaseModel):
    category: FaultCategory
    confidence: float = Field(default=0.5, ge=0, le=1)
    evidence: list[str] = Field(default_factory=list)
    needs_user_input: bool = False

class VehicleSnapshot(BaseModel):
    model_config = ConfigDict(extra='allow')
    vehicle_no: str
    device_type: str | None = None
    vehicle_type: str | None = None
    last_update: datetime | None = None
    minutes_since_last_update: float | None = None
    state: str | None = None
    vehicle_status: str | None = None
    device_status: str | None = None
    logger: bool | None = None
    satellites: int | None = None
    battery_connected: bool | None = None
    battery: float | None = None
    gsm_signals: int | None = None
    subscription_due: datetime | None = None
    imei: str | None = None
    sim_no: str | None = None
    operator: str | None = None
    address: str | None = None
    port: int | str | None = None
    since: datetime | None = None
    hours_since_status: float | None = None
    days_since_status: float | None = None
    raw_payload: dict[str, Any] = Field(default_factory=dict)

class CommandSpec(BaseModel):
    id: str
    order: int
    command: str
    purpose: str
    how_to_send: str
    output_schema: dict[str, Any] = Field(default_factory=dict)
    analysis: dict[str, Any] = Field(default_factory=dict)
    next_if_inconclusive: list[str] = Field(default_factory=list)

class TicketResult(BaseModel):
    ticket_id: str
    status: str = 'created'
    assigned_to: str | None = None
    summary: str = ''

class ChatMessage(BaseModel):
    id: str
    role: str
    content: str
    created_at: str
    attachment_name: str | None = None

class SessionSummary(BaseModel):
    session_id: str
    title: str
    created_at: str
    updated_at: str
    status: str = 'open'
    vehicle_no: str | None = None
    last_message: str = ''


class WorkflowFrame(BaseModel):
    """Typed schema for a pauseable/resumable workflow frame in the session stack."""
    frame_id: str
    type: str
    status: Literal['active', 'paused', 'stale', 'done', 'escalated'] = 'active'
    current_node: str | None = None
    awaiting: str = 'none'
    paused_at_step: str | None = None
    paused_at: datetime | None = None
    resume_hint: str | None = None
    context: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    outcome: str | None = None
    summary: str | None = None
    completed_at: datetime | None = None
