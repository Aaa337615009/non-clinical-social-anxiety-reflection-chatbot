from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


class ConversationState(str, Enum):
    OPENING = "OPENING"
    ISSUE_IDENTIFICATION = "ISSUE_IDENTIFICATION"
    EXPERIENCE_MAPPING = "EXPERIENCE_MAPPING"
    RATIONALE_AND_PERMISSION = "RATIONALE_AND_PERMISSION"
    ASSUMPTION_EXAMINATION = "ASSUMPTION_EXAMINATION"
    EVIDENCE_EXAMINATION = "EVIDENCE_EXAMINATION"
    ALTERNATIVE_INTERPRETATIONS = "ALTERNATIVE_INTERPRETATIONS"
    COLLABORATIVE_REAPPRAISAL = "COLLABORATIVE_REAPPRAISAL"
    SUMMARY_AND_SUPPORT = "SUMMARY_AND_SUPPORT"
    FEEDBACK_AND_CLOSURE = "FEEDBACK_AND_CLOSURE"


STATE_SEQUENCE = tuple(ConversationState)


VISIBLE_STAGE_BY_STATE = {
    ConversationState.OPENING: 1,
    ConversationState.ISSUE_IDENTIFICATION: 2,
    ConversationState.EXPERIENCE_MAPPING: 3,
    ConversationState.RATIONALE_AND_PERMISSION: 4,
    ConversationState.ASSUMPTION_EXAMINATION: 5,
    ConversationState.EVIDENCE_EXAMINATION: 5,
    ConversationState.ALTERNATIVE_INTERPRETATIONS: 5,
    ConversationState.COLLABORATIVE_REAPPRAISAL: 6,
    ConversationState.SUMMARY_AND_SUPPORT: 7,
    ConversationState.FEEDBACK_AND_CLOSURE: 8,
}

class SessionStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    STOPPED = "stopped"
    COMPLETED = "completed"


class RiskLevel(str, Enum):
    NONE = "none"
    ELEVATED = "elevated"
    IMMINENT = "imminent"


class MessageRole(str, Enum):
    PARTICIPANT = "participant"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class SlotSource(str, Enum):
    EXPLICIT_USER_STATEMENT = "explicit_user_statement"
    REASONABLE_INFERENCE = "reasonable_inference"
    MISSING = "missing"


class CaseSlot(BaseModel):
    value: str = Field(default="", max_length=1200)
    source: SlotSource = SlotSource.MISSING
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    needs_clarification: bool = True


class CaseFormulation(BaseModel):
    observable_event: str = Field(default="", max_length=1200)
    other_person_response: str = Field(default="", max_length=1200)
    user_action: str = Field(default="", max_length=1200)
    automatic_thought: str = Field(default="", max_length=1200)
    emotion: str = Field(default="", max_length=600)
    central_negative_interpretation: str = Field(default="", max_length=1200)
    feared_meaning: str = Field(default="", max_length=1200)
    evidence_for: list[str] = Field(default_factory=list, max_length=8)
    evidence_not_supporting: list[str] = Field(default_factory=list, max_length=8)
    uncertainty: list[str] = Field(default_factory=list, max_length=8)
    alternatives_already_considered: list[str] = Field(default_factory=list, max_length=8)
    user_goal: str = Field(default="", max_length=1200)


class CaseState(BaseModel):
    event: CaseSlot = Field(default_factory=CaseSlot)
    response: CaseSlot = Field(default_factory=CaseSlot)
    thought: CaseSlot = Field(default_factory=CaseSlot)
    emotion: CaseSlot = Field(default_factory=CaseSlot)
    recap_presented: bool = False
    recap_confirmed: bool = False
    reflection_permission_requested: bool = False
    reflection_permission_granted: bool = False
    formulation: CaseFormulation = Field(default_factory=CaseFormulation)


CASE_SLOT_NAMES = ("event", "response", "thought", "emotion")


class EmotionalIntensity(str, Enum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"


class ValidationLength(str, Enum):
    NONE = "none"
    BRIEF = "brief"
    EXTENDED = "extended"


class SummaryCard(BaseModel):
    situation: str = ""
    feelings: str = ""
    initial_interpretation: str = ""
    evidence_and_uncertainties: str = ""
    alternative_interpretation: str = ""
    possible_interpretations: list[str] = Field(default_factory=list, max_length=4)
    balanced_reappraisal: str = ""
    possible_next_steps: list[str] = Field(default_factory=list, max_length=2)
    status: str = "draft"

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_next_step_fields(cls, value: Any) -> Any:
        """Accept older JSON cards while exposing one canonical field to the app."""
        if not isinstance(value, dict):
            return value
        payload = dict(value)
        if not payload.get("possible_next_steps"):
            legacy_value: Any = None
            for legacy_name in (
                "possible_next_step",
                "next_step",
                "next_steps",
                "support_next_step",
            ):
                if payload.get(legacy_name):
                    legacy_value = payload[legacy_name]
                    break
            if isinstance(legacy_value, str):
                migrated = [
                    line.strip().lstrip("•- ").strip()
                    for line in legacy_value.splitlines()
                    if line.strip().lstrip("•- ").strip()
                ]
                payload["possible_next_steps"] = migrated[:2]
            elif isinstance(legacy_value, (list, tuple)):
                payload["possible_next_steps"] = [
                    str(item).strip()
                    for item in legacy_value
                    if str(item).strip()
                ][:2]
        return payload

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str) -> str:
        if value not in {"draft", "confirmed", "modified"}:
            raise ValueError("Invalid summary status")
        return value


class AssistantTurn(BaseModel):
    message: str = Field(min_length=1, max_length=2500)
    next_state: ConversationState
    stage_complete: bool = False
    permission_granted: bool | None = None
    case_state: CaseState = Field(default_factory=CaseState)
    emotional_intensity: EmotionalIntensity = EmotionalIntensity.LOW
    validation_needed: bool = False
    validation_length: ValidationLength = ValidationLength.NONE
    reflection_target: str = Field(default="", max_length=1200)
    grounding_detail: str = Field(default="", max_length=1200)
    question_purpose: str = Field(default="", max_length=800)
    new_information_needed: str = Field(default="", max_length=800)
    unsupported_inference_detected: bool = False
    repeated_question_detected: bool = False
    risk_level: RiskLevel = RiskLevel.NONE
    risk_reason: str = Field(default="", max_length=500)
    summary_card: SummaryCard | None = None
    should_offer_feedback: bool = False
    quick_replies: list[str] = Field(default_factory=list, max_length=3)


class SessionRecord(BaseModel):
    id: str
    participant_id: str
    consented_at: datetime
    status: SessionStatus
    current_state: ConversationState
    risk_level: RiskLevel = RiskLevel.NONE
    summary_card: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime


class MessageRecord(BaseModel):
    id: int | str
    session_id: str
    role: MessageRole
    content: str
    state: ConversationState
    kind: str = "chat"
    risk_level: RiskLevel = RiskLevel.NONE
    created_at: datetime


class FeedbackRecord(BaseModel):
    id: int | str
    session_id: str
    helpfulness: int
    felt_understood: bool
    comments: str = ""
    created_at: datetime


def next_state(current: ConversationState) -> ConversationState:
    index = STATE_SEQUENCE.index(current)
    if index == len(STATE_SEQUENCE) - 1:
        return current
    return STATE_SEQUENCE[index + 1]


def clamp_next_state(
    current: ConversationState, proposed: ConversationState
) -> ConversationState:
    """Allow staying put or advancing one step; never skip the protocol."""
    allowed = {current, next_state(current)}
    return proposed if proposed in allowed else next_state(current)


def slot_is_sufficient(slot: CaseSlot) -> bool:
    return bool(
        slot.value.strip()
        and slot.source is not SlotSource.MISSING
        and not slot.needs_clarification
        and slot.confidence >= 0.6
    )


def missing_case_slots(case_state: CaseState) -> list[str]:
    return [
        name
        for name in CASE_SLOT_NAMES
        if not slot_is_sufficient(getattr(case_state, name))
    ]


def merge_case_state(previous: CaseState, update: CaseState) -> CaseState:
    """Merge semantic slot updates without turning weak inferences into user facts."""
    merged = previous.model_copy(deep=True)
    for name in CASE_SLOT_NAMES:
        old = getattr(previous, name)
        new = getattr(update, name)
        if new.source is SlotSource.EXPLICIT_USER_STATEMENT and new.value.strip():
            setattr(merged, name, new.model_copy(deep=True))
        elif old.source is SlotSource.EXPLICIT_USER_STATEMENT:
            continue
        elif new.source is SlotSource.REASONABLE_INFERENCE and new.value.strip():
            setattr(merged, name, new.model_copy(deep=True))
        elif not old.value.strip():
            setattr(merged, name, new.model_copy(deep=True))
    merged.recap_presented = previous.recap_presented or update.recap_presented
    merged.recap_confirmed = update.recap_confirmed
    merged.reflection_permission_requested = (
        previous.reflection_permission_requested
        or update.reflection_permission_requested
    )
    merged.reflection_permission_granted = (
        previous.reflection_permission_granted
        or update.reflection_permission_granted
    )
    formulation = previous.formulation.model_copy(deep=True)
    update_formulation = update.formulation
    for name in (
        "observable_event",
        "other_person_response",
        "user_action",
        "automatic_thought",
        "emotion",
        "central_negative_interpretation",
        "feared_meaning",
        "user_goal",
    ):
        value = getattr(update_formulation, name).strip()
        if value:
            setattr(formulation, name, value)
    for name in (
        "evidence_for",
        "evidence_not_supporting",
        "uncertainty",
        "alternatives_already_considered",
    ):
        values = [item.strip() for item in getattr(formulation, name) if item.strip()]
        for item in getattr(update_formulation, name):
            clean = item.strip()
            if clean and clean.casefold() not in {value.casefold() for value in values}:
                values.append(clean)
        setattr(formulation, name, values[:8])
    if not formulation.observable_event and merged.event.value.strip():
        formulation.observable_event = merged.event.value.strip()
    if not formulation.automatic_thought and merged.thought.value.strip():
        formulation.automatic_thought = merged.thought.value.strip()
    if not formulation.emotion and merged.emotion.value.strip():
        formulation.emotion = merged.emotion.value.strip()
    merged.formulation = formulation
    return merged


def resolve_state_transition(
    current: ConversationState,
    turn: AssistantTurn,
    case_state: CaseState | None = None,
) -> ConversationState:
    """Advance only when the current protocol stage's completion rule is satisfied."""
    if current is ConversationState.EXPERIENCE_MAPPING:
        mapped = case_state or turn.case_state
        if turn.stage_complete and not missing_case_slots(mapped):
            return ConversationState.RATIONALE_AND_PERMISSION
        return current
    if current is ConversationState.RATIONALE_AND_PERMISSION:
        return (
            ConversationState.ASSUMPTION_EXAMINATION
            if turn.stage_complete and turn.permission_granted is True
            else current
        )
    if current is ConversationState.COLLABORATIVE_REAPPRAISAL:
        return current
    if turn.stage_complete:
        return next_state(current)
    return current


def visible_stage(state: ConversationState) -> int:
    return VISIBLE_STAGE_BY_STATE[state]
