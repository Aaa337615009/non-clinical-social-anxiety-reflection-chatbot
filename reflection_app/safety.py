from __future__ import annotations

import re

from .models import AssistantTurn, ConversationState, RiskLevel


IMMINENT_PATTERNS = (
    r"\b(kill|hurt) myself\b",
    r"\bend (my|this) life\b",
    r"\bsuicid(?:e|al)\b",
    r"\bcan't keep (myself|me) safe\b",
    r"\bplan to (die|kill myself)\b",
    r"\b(?:i am|i'm|i plan|i want) to (?:kill|seriously hurt) (?:him|her|them|someone)\b",
    r"自杀",
    r"杀死自己",
    r"伤害自己",
    r"不想活(?:了|下去)?",
    r"活不下去",
    r"结束生命",
    r"(?:我要|我想|我计划)(?:杀了|严重伤害)(?:他|她|他们|别人)",
)

ELEVATED_PATTERNS = (
    r"\bwish I (?:wasn't|were not) alive\b",
    r"\bbetter off dead\b",
    r"\bself[- ]harm\b",
    r"消失就好",
    r"死了算了",
    r"没有活着的意义",
)


DEFAULT_CRISIS_SUPPORT = (
    "Thank you for telling me. Your immediate safety matters more than continuing this reflection. "
    "If you or someone else may be in immediate danger, call your local emergency number now; "
    "in the UK call 999 or go to A&E. For urgent mental health support in the UK, call 111 and "
    "choose the mental health option. You can also call Samaritans free at 116 123 at any time. "
    "If you are outside the UK, contact your local emergency or crisis service. If possible, tell "
    "someone you trust who can stay with you. Are you in immediate danger right now?"
)


def detect_risk(text: str) -> tuple[RiskLevel, str]:
    normalized = text.casefold()
    for pattern in IMMINENT_PATTERNS:
        if re.search(pattern, normalized, flags=re.IGNORECASE):
            return RiskLevel.IMMINENT, "deterministic_imminent_phrase"
    for pattern in ELEVATED_PATTERNS:
        if re.search(pattern, normalized, flags=re.IGNORECASE):
            return RiskLevel.ELEVATED, "deterministic_elevated_phrase"
    return RiskLevel.NONE, ""


def crisis_turn(
    current_state: ConversationState,
    custom_support_text: str = "",
) -> AssistantTurn:
    return AssistantTurn(
        message=custom_support_text or DEFAULT_CRISIS_SUPPORT,
        next_state=current_state,
        risk_level=RiskLevel.IMMINENT,
        risk_reason="deterministic safety escalation",
        should_offer_feedback=False,
    )
