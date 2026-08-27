from __future__ import annotations

import json
import re
from collections.abc import Sequence
from difflib import SequenceMatcher
from typing import Any

from openai import OpenAI

from .models import (
    AssistantTurn,
    CaseSlot,
    CaseState,
    ConversationState,
    EmotionalIntensity,
    MessageRecord,
    RiskLevel,
    SlotSource,
    SummaryCard,
    ValidationLength,
    merge_case_state,
    missing_case_slots,
    next_state,
    resolve_state_transition,
)
from .prompts import (
    DEFAULT_STAGE_FOUR_PROMPT,
    DEFAULT_STAGE_THREE_RECAP,
    STATE_QUESTIONS,
    STATE_GOALS,
    SUMMARY_PROMPT,
    SYSTEM_PROMPT,
    is_unsure,
    prompt_for_state,
    quick_replies_for_state,
    skip_entry_prompt,
    unsure_prompt,
)
from .safety import crisis_turn, detect_risk


def enforce_single_question(message: str) -> str:
    """Keep the first question and turn later question marks into full stops."""
    seen = False
    output: list[str] = []
    for char in message.strip():
        if char in {"?", "？"}:
            output.append("." if seen else char)
            seen = True
        else:
            output.append(char)
    return re.sub(r"\s+", " ", "".join(output)).strip()


def normalise_validation_plan(turn: AssistantTurn) -> AssistantTurn:
    if turn.emotional_intensity is EmotionalIntensity.LOW:
        if not turn.validation_needed:
            turn.validation_length = ValidationLength.NONE
    elif turn.emotional_intensity is EmotionalIntensity.HIGH:
        turn.validation_needed = True
        turn.validation_length = ValidationLength.EXTENDED
    elif turn.validation_needed and turn.validation_length is ValidationLength.NONE:
        turn.validation_length = ValidationLength.BRIEF
    return turn


SPECIAL_CHOICE_STATES = {
    ConversationState.RATIONALE_AND_PERMISSION,
    ConversationState.SUMMARY_AND_SUPPORT,
    ConversationState.FEEDBACK_AND_CLOSURE,
}

STOCK_VALIDATION_PATTERNS = (
    r"^it(?:'|’)s completely understandable\b",
    r"^that sounds really difficult\b",
    r"^it sounds quite painful\b",
    r"^thank you for sharing that\b",
    r"^sometimes actions can feel ambiguous\b",
)

INTERNAL_OUTPUT_PATTERN = re.compile(
    r"\b(?:participant|case_state|explicit_user_statement|reasonable_inference|"
    r"needs_clarification|confidence)\b|\b(?:event|response|thought|emotion)\s*:",
    re.I,
)

META_CHOICE_PATTERN = re.compile(
    r"\b(?:pause|resume|end (?:the )?(?:conversation|chat)|stop (?:the )?(?:conversation|chat)|"
    r"finish (?:the )?(?:conversation|chat)|keep talking|continue (?:the )?(?:conversation|chat)|"
    r"prefer to (?:pause|stop|end|finish|continue)|explore (?:anything|something) else|"
    r"anything else (?:you(?:'d| would) like|to explore))\b",
    re.I,
)

QUICK_REPLY_ACTION_PATTERN = re.compile(
    r"\b(?:pause|resume|end|stop|finish|continue|keep talking|skip)\b",
    re.I,
)

PAUSE_RESUME_PATTERN = re.compile(r"\b(?:pause|resume)\b", re.I)


def _sentences(message: str) -> list[str]:
    return [
        part.strip()
        for part in re.split(r"(?<=[.!?])\s+", re.sub(r"\s+", " ", message).strip())
        if part.strip()
    ]


def _is_stock_validation(sentence: str) -> bool:
    return any(re.search(pattern, sentence.strip(), re.I) for pattern in STOCK_VALIDATION_PATTERNS)


def _recent_openings(history: Sequence[MessageRecord]) -> set[str]:
    openings: set[str] = set()
    for item in history[-8:]:
        if item.role.value != "assistant" or item.kind != "chat":
            continue
        parts = _sentences(item.content)
        if parts:
            openings.add(parts[0].casefold().rstrip(".!?"))
    return openings


PERMISSION_PATTERN = re.compile(
    r"\b(?:may i ask|may we|is it (?:alright|all right|okay)|is that (?:alright|all right|okay)|"
    r"would that be (?:alright|all right|okay)|would it be (?:alright|all right|okay)|"
    r"would it feel (?:alright|all right|okay)|would you be (?:comfortable|willing))\b",
    re.I,
)

REFLECTION_STATES = {
    ConversationState.ASSUMPTION_EXAMINATION,
    ConversationState.EVIDENCE_EXAMINATION,
    ConversationState.ALTERNATIVE_INTERPRETATIONS,
    ConversationState.COLLABORATIVE_REAPPRAISAL,
}

GENERIC_QUESTION_PATTERNS = (
    r"\bcan you tell me more\b",
    r"\bwhat other thoughts or feelings\b",
    r"\bhow does that affect you\b",
    r"\bwhat would you like to clarify next\b",
    r"\bis there anything else\b",
    r"\bwhat (?:else|more) would you like\b",
)

UNSUPPORTED_INFERENCE_TERMS = (
    "jealousy",
    "jealous",
    "attachment issues",
    "insecurity",
    "insecure",
    "manipulation",
    "manipulative",
    "attention-seeking",
    "attention seeking",
)

STEREOTYPE_PATTERN = re.compile(
    r"\b(?:(?:women|men|girls|boys|older people|younger people|friends|partners|"
    r"roommates|colleagues|people in relationships)\s+(?:always|usually|typically|"
    r"tend to|are (?:naturally|generally|typically))|people from [a-z -]+ "
    r"(?:cultures?|backgrounds?)\s+(?:always|usually|typically|tend to)|"
    r"because\s+(?:she|he|they)\s+"
    r"(?:is|are)\s+(?:a\s+|an\s+)?(?:woman|man|girl|boy|young|old)|"
    r"(?:cultural|gender|age|relationship)\s+stereotype)\b",
    re.I,
)


def _safe_stage_three_recap(message: str) -> str:
    """Keep Stage 3's recap natural, internal-field-free and question-free."""
    candidate = re.sub(r"\s+", " ", message).strip()
    if (
        not candidate
        or ";" in candidate
        or INTERNAL_OUTPUT_PATTERN.search(candidate)
        or META_CHOICE_PATTERN.search(candidate)
        or any(_is_stock_validation(sentence) for sentence in _sentences(candidate))
        or "?" in candidate
        or PERMISSION_PATTERN.search(candidate)
    ):
        return DEFAULT_STAGE_THREE_RECAP
    return candidate


def sanitise_quick_replies(replies: Sequence[str]) -> list[str]:
    """Keep only concise answers to the current question, not duplicate app controls."""
    clean: list[str] = []
    for reply in replies:
        value = re.sub(r"\s+", " ", reply).strip()
        if not value or QUICK_REPLY_ACTION_PATTERN.search(value):
            continue
        if value.casefold() in {item.casefold() for item in clean}:
            continue
        clean.append(value)
        if len(clean) == 3:
            break
    return clean


def _participant_text(history: Sequence[MessageRecord], user_text: str = "") -> str:
    parts = [
        item.content
        for item in history
        if item.role.value == "participant" and item.kind == "chat"
    ]
    if user_text.strip():
        parts.append(user_text.strip())
    return " ".join(parts)


def _question_text(message: str) -> str:
    return next((part for part in _sentences(message) if "?" in part), "")


def _normalised_question(message: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", "", _question_text(message).casefold())


def _previous_questions(history: Sequence[MessageRecord]) -> list[str]:
    return [
        _normalised_question(item.content)
        for item in history
        if item.role.value == "assistant" and item.kind == "chat" and "?" in item.content
    ]


def _meaningful_tokens(text: str) -> set[str]:
    stop = {
        "about", "after", "again", "could", "from", "have", "into", "might", "other",
        "that", "their", "there", "these", "they", "this", "what", "when", "where",
        "which", "with", "would", "your", "were", "been", "being", "just", "more",
    }
    return {
        token
        for token in re.findall(r"[a-z0-9']+", text.casefold())
        if len(token) >= 4 and token not in stop
    }


def quality_rejection_reasons(
    turn: AssistantTurn,
    state: ConversationState,
    history: Sequence[MessageRecord],
    user_text: str,
) -> list[str]:
    """Return executable reasons to reject a vague, repeated or ungrounded Stage 5/6 turn."""
    if state not in REFLECTION_STATES:
        return []
    reasons: list[str] = []
    question = _question_text(turn.message)
    if not question:
        reasons.append("missing one substantive question")
    if any(re.search(pattern, question, re.I) for pattern in GENERIC_QUESTION_PATTERNS):
        reasons.append("generic question")
    if PERMISSION_PATTERN.search(turn.message):
        reasons.append("permission was already handled")
    if turn.repeated_question_detected:
        reasons.append("model marked the question repeated")
    normalised = _normalised_question(turn.message)
    if normalised and any(
        previous
        and SequenceMatcher(None, normalised, previous).ratio() >= 0.82
        for previous in _previous_questions(history)
    ):
        reasons.append("question repeats an earlier assistant question")

    corpus = _participant_text(history, user_text)
    lower_corpus = corpus.casefold()
    complete_output = " ".join([turn.message, *turn.quick_replies])
    unsupported_terms = [
        term
        for term in UNSUPPORTED_INFERENCE_TERMS
        if term in complete_output.casefold() and term not in lower_corpus
    ]
    if turn.unsupported_inference_detected or unsupported_terms or STEREOTYPE_PATTERN.search(complete_output):
        reasons.append("unsupported motive, trait or stereotype")
    if state is ConversationState.ALTERNATIVE_INTERPRETATIONS and not re.search(
        r"\b(?:possible|possibility|might|may|could|perhaps)\b",
        complete_output,
        re.I,
    ):
        reasons.append("alternative interpretation is not tentative")

    detail = turn.grounding_detail.strip()
    detail_tokens = _meaningful_tokens(detail)
    if (
        not detail
        or not detail_tokens
        or not detail_tokens.intersection(_meaningful_tokens(corpus))
        or not detail_tokens.intersection(_meaningful_tokens(turn.message))
    ):
        reasons.append("question is not grounded in a participant-provided detail")
    if not turn.reflection_target.strip():
        reasons.append("missing reflection target")
    if not turn.question_purpose.strip() or not turn.new_information_needed.strip():
        reasons.append("missing stage-specific purpose")
    return list(dict.fromkeys(reasons))


def _case_detail(case_state: CaseState, history: Sequence[MessageRecord], user_text: str) -> str:
    formulation = case_state.formulation
    candidates = (
        formulation.other_person_response,
        formulation.observable_event,
        case_state.response.value,
        case_state.event.value,
        user_text,
    )
    for candidate in candidates:
        value = re.sub(r"\s+", " ", candidate).strip().strip(".?!")
        if value:
            return value[:220]
    participant = _participant_text(history, user_text)
    return participant[-220:].strip().strip(".?!") or "the change you noticed"


def grounded_fallback_turn(
    turn: AssistantTurn,
    state: ConversationState,
    history: Sequence[MessageRecord],
    user_text: str,
) -> AssistantTurn:
    """Produce one deterministic, case-grounded question after the single retry is rejected."""
    detail = _case_detail(turn.case_state, history, user_text)
    quoted = f'"{detail}"'
    templates = {
        ConversationState.ASSUMPTION_EXAMINATION: (
            f"Thinking about {quoted}, what did that seem to say about how you were being viewed?",
            "identify the central interpretation",
            "the meaning the participant attached to the specific moment",
        ),
        ConversationState.EVIDENCE_EXAMINATION: (
            f"Apart from {quoted}, what did the other person directly say or do that supported that interpretation?",
            "separate observation from interpretation",
            "direct evidence supporting the interpretation",
        ),
        ConversationState.ALTERNATIVE_INTERPRETATIONS: (
            f"Could {quoted} fit another possible explanation, or what makes that less likely?",
            "consider an evidence-compatible alternative",
            "the participant's own possible alternative",
        ),
        ConversationState.COLLABORATIVE_REAPPRAISAL: (
            f"Would it feel accurate to say that {quoted} mattered, while its meaning is still uncertain?",
            "form a balanced, tentative reflection",
            "whether the proposed uncertainty feels credible",
        ),
    }
    message, purpose, needed = templates[state]
    turn.message = message
    turn.next_state = state
    turn.grounding_detail = detail
    turn.reflection_target = detail
    turn.question_purpose = purpose
    turn.new_information_needed = needed
    turn.unsupported_inference_detected = False
    turn.repeated_question_detected = False
    turn.quick_replies = []
    return turn


def normalise_assistant_message(
    turn: AssistantTurn,
    state: ConversationState,
    history: Sequence[MessageRecord],
) -> str:
    """Apply participant-facing conversation rules after structured generation."""
    message = enforce_single_question(turn.message)
    if INTERNAL_OUTPUT_PATTERN.search(message):
        return (
            DEFAULT_STAGE_FOUR_PROMPT
            if state is ConversationState.RATIONALE_AND_PERMISSION
            else STATE_QUESTIONS[state]
        )

    sentences = [
        sentence
        for sentence in _sentences(message)
        if not _is_stock_validation(sentence) and not PAUSE_RESUME_PATTERN.search(sentence)
    ]
    if state is not ConversationState.RATIONALE_AND_PERMISSION:
        sentences = [sentence for sentence in sentences if not PERMISSION_PATTERN.search(sentence)]
    if state not in SPECIAL_CHOICE_STATES:
        sentences = [sentence for sentence in sentences if not META_CHOICE_PATTERN.search(sentence)]

    if state in SPECIAL_CHOICE_STATES:
        return enforce_single_question(" ".join(sentences)) or STATE_QUESTIONS[state]

    if (
        state is ConversationState.COLLABORATIVE_REAPPRAISAL
        and turn.stage_complete
        and not sentences
    ):
        return "We have developed a basic reflection that keeps more than one possibility open."

    question_index = next((index for index, sentence in enumerate(sentences) if "?" in sentence), None)
    if question_index is None:
        if state is ConversationState.COLLABORATIVE_REAPPRAISAL and turn.stage_complete:
            return " ".join(sentences).strip() or (
                "We have developed a basic reflection that keeps more than one possibility open."
            )
        return STATE_QUESTIONS[state]

    question = sentences[question_index]
    validation = sentences[:question_index]
    if turn.emotional_intensity is EmotionalIntensity.LOW or not turn.validation_needed:
        validation = []
    else:
        maximum = 2 if turn.emotional_intensity is EmotionalIntensity.HIGH else 1
        validation = validation[-maximum:]
        recent = _recent_openings(history)
        validation = [
            sentence
            for sentence in validation
            if sentence.casefold().rstrip(".!?") not in recent
        ]
    return enforce_single_question(" ".join([*validation, question]))


EXPERIENCE_SLOT_QUESTIONS = {
    "event": "What actually happened in that moment?",
    "response": (
        "Was there anything the other person said or did—or anything you did in response—"
        "that led you to that interpretation?"
    ),
    "thought": "What did you think that moment might mean?",
    "emotion": "What feeling was strongest for you then?",
}


def normalise_experience_mapping_turn(turn: AssistantTurn) -> AssistantTurn:
    """Make the model's semantic slots, rather than its prose, control Stage 3."""
    missing = missing_case_slots(turn.case_state)
    turn.quick_replies = []
    turn.summary_card = None
    if missing:
        question = EXPERIENCE_SLOT_QUESTIONS[missing[0]]
        if turn.validation_needed and turn.emotional_intensity is EmotionalIntensity.HIGH:
            question = f"I can hear how intense that uncertainty feels. {question}"
        elif turn.validation_needed and turn.emotional_intensity is EmotionalIntensity.MODERATE:
            question = f"That uncertainty is understandably unsettling. {question}"
        turn.message = question
        turn.next_state = ConversationState.EXPERIENCE_MAPPING
        turn.stage_complete = False
        return turn

    turn.case_state.recap_presented = True
    turn.case_state.reflection_permission_requested = True
    turn.message = _safe_stage_three_recap(turn.message)
    turn.next_state = ConversationState.RATIONALE_AND_PERMISSION
    turn.stage_complete = True
    return turn


def _tentative(text: str, index: int) -> str:
    value = text.strip().rstrip(".")
    if not value:
        value = "the moment may have had more than one explanation"
    tentative = re.compile(r"\b(possible|possibility|might|may|could|perhaps)\b", re.I)
    if tentative.search(value):
        return f"{value}."
    prefixes = ("One possibility is that", "It might be that", "A possible explanation is that")
    return f"{prefixes[index % len(prefixes)]} {value[0].lower() + value[1:]}."


def _contains_unsupported_inference(text: str, participant_text: str) -> bool:
    lower_text = text.casefold()
    lower_participant = participant_text.casefold()
    return any(term in lower_text and term not in lower_participant for term in UNSUPPORTED_INFERENCE_TERMS)


def ensure_possible_interpretations(
    card: SummaryCard,
    participant_text: str = "",
) -> SummaryCard:
    candidates = [
        item
        for item in card.possible_interpretations
        if item.strip() and not _contains_unsupported_inference(item, participant_text)
    ]
    if card.alternative_interpretation.strip():
        if not _contains_unsupported_inference(card.alternative_interpretation, participant_text):
            candidates.append(card.alternative_interpretation)
    if len(candidates) < 2:
        candidates.extend(
            [
                "One possibility is that the response reflected factors that were not directly observable.",
                "It might be that the event was more ambiguous than it felt in the moment.",
            ]
        )
    unique: list[str] = []
    for candidate in candidates:
        normalised = _tentative(candidate, len(unique))
        if normalised.casefold() not in {item.casefold() for item in unique}:
            unique.append(normalised)
        if len(unique) == 4:
            break
    card.possible_interpretations = unique[:4]
    card.alternative_interpretation = "\n".join(f"• {item}" for item in card.possible_interpretations)
    card.status = "draft"
    return card


OPTIONAL_STEP_PATTERN = re.compile(
    r"\b(?:might consider|if it feels right|one possible next step could be|you could|you may)\b",
    re.I,
)


def ensure_possible_next_steps(
    card: SummaryCard,
    case_state: CaseState | None = None,
    participant_text: str = "",
) -> SummaryCard:
    """Keep one or two case-specific, autonomous next steps on every draft card."""
    mapped = case_state or CaseState()
    event = (
        mapped.formulation.observable_event.strip()
        or mapped.event.value.strip()
        or card.situation.strip()
        or "the change you noticed"
    )
    case_text = " ".join(
        (
            participant_text,
            event,
            mapped.formulation.other_person_response,
            mapped.formulation.user_action,
            mapped.formulation.automatic_thought,
            mapped.formulation.user_goal,
            card.situation,
        )
    )
    case_tokens = _meaningful_tokens(case_text)
    steps = []
    for item in card.possible_next_steps:
        clean = re.sub(r"\s+", " ", item).strip()
        if not clean or _contains_unsupported_inference(clean, participant_text):
            continue
        if case_tokens and not _meaningful_tokens(clean).intersection(case_tokens):
            continue
        steps.append(clean)
    if not steps:
        steps = [
            f'You might consider reminding yourself: "I noticed {event.rstrip(".?!")}, but I do not yet know why it happened."'
        ]
    normalised: list[str] = []
    for step in steps:
        value = step
        if not OPTIONAL_STEP_PATTERN.search(value):
            value = f"You might consider {value[0].lower() + value[1:]}"
        if value.casefold() not in {item.casefold() for item in normalised}:
            normalised.append(value)
        if len(normalised) == 2:
            break
    card.possible_next_steps = normalised
    return card


def build_fallback_summary(
    messages: Sequence[MessageRecord],
    latest_text: str = "",
    latest_state: ConversationState | None = None,
    case_state: CaseState | None = None,
) -> SummaryCard:
    participant_items = [
        item
        for item in messages
        if item.role.value == "participant" and item.kind == "chat" and not is_unsure(item.content)
    ]
    participant_messages = [item.content for item in participant_items]
    by_state: dict[ConversationState, list[str]] = {}
    for item in participant_items:
        by_state.setdefault(item.state, []).append(item.content)
    if latest_text.strip() and not is_unsure(latest_text):
        participant_messages.append(latest_text.strip())
        if latest_state is not None:
            by_state.setdefault(latest_state, []).append(latest_text.strip())

    mapped = case_state or CaseState()
    situation = mapped.event.value.strip() or (
        by_state.get(ConversationState.OPENING, participant_messages[:1]) or ["Not yet established"]
    )[0]
    feelings = mapped.emotion.value.strip() or "The feeling was not yet clearly established"
    initial = mapped.thought.value.strip() or (
        by_state.get(ConversationState.ASSUMPTION_EXAMINATION) or ["The original meaning was not yet established"]
    )[-1]
    response = mapped.response.value.strip()
    evidence = (
        by_state.get(ConversationState.EVIDENCE_EXAMINATION)
        or ["Only the details the participant described are known; other parts remain uncertain"]
    )[-1]
    alternative_seed = (
        by_state.get(ConversationState.ALTERNATIVE_INTERPRETATIONS)
        or ["the other person's response may have reflected circumstances the participant could not observe"]
    )[-1]
    balanced_seed = (
        by_state.get(ConversationState.COLLABORATIVE_REAPPRAISAL)
        or ["The original interpretation is understandable, but it is not the only possible account"]
    )[-1]
    card = SummaryCard(
        situation=situation,
        feelings=feelings,
        initial_interpretation=initial,
        evidence_and_uncertainties=(
            f"Observed: {situation}. Participant response: {response or 'not clearly established'}. "
            f"Uncertainty: {evidence}."
        ),
        possible_interpretations=[
            alternative_seed,
            "the event might have been more ambiguous than the original interpretation suggested",
        ],
        balanced_reappraisal=(
            f"{balanced_seed.rstrip('.')}. This is one possible reflection, not a statement of fact."
        ),
        possible_next_steps=[
            f'You might consider reminding yourself: "I noticed {situation.rstrip(".?!")}, but I do not yet know why it happened."'
        ],
    )
    participant_text = " ".join(participant_messages)
    card = ensure_possible_interpretations(card, participant_text)
    return ensure_possible_next_steps(card, mapped, participant_text)


class ReflectionEngine:
    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        crisis_support_text: str = "",
        client: Any | None = None,
    ) -> None:
        self.model = model
        self.crisis_support_text = crisis_support_text
        self.client = client or OpenAI(api_key=api_key)

    def respond(
        self,
        current_state: ConversationState,
        history: Sequence[MessageRecord],
        user_text: str,
        case_state: CaseState | None = None,
    ) -> AssistantTurn:
        current_case = case_state or CaseState()
        deterministic_risk, reason = detect_risk(user_text)
        if deterministic_risk is RiskLevel.IMMINENT:
            turn = crisis_turn(current_state, self.crisis_support_text)
            turn.risk_reason = reason
            turn.case_state = current_case
            return turn

        base_instructions = SYSTEM_PROMPT.format(
            current_state=current_state.value,
            expected_next_state=next_state(current_state).value,
            state_goal=STATE_GOALS[current_state],
            case_state=current_case.model_dump_json(),
        )
        transcript = [
            {
                "role": "assistant" if item.role.value == "assistant" else "user",
                "content": item.content,
            }
            for item in history[-30:]
            if item.kind == "chat" and item.role.value != "system"
        ]
        transcript.append({"role": "user", "content": user_text})
        rejection_feedback = ""
        for attempt in range(2):
            instructions = base_instructions
            if rejection_feedback:
                instructions += (
                    "\n\nThe previous draft was rejected by the application quality gate for: "
                    f"{rejection_feedback}. Regenerate once with one concrete, non-repeated, "
                    "case-grounded question and no unsupported inference or permission request."
                )
            response = self.client.responses.parse(
                model=self.model,
                input=[{"role": "developer", "content": instructions}, *transcript],
                text_format=AssistantTurn,
                store=False,
                max_output_tokens=1800,
            )
            turn = response.output_parsed
            if turn is None:
                raise RuntimeError("The model returned no structured output.")
            if turn.risk_level is RiskLevel.IMMINENT:
                safe_turn = crisis_turn(current_state, self.crisis_support_text)
                safe_turn.risk_reason = turn.risk_reason or "model_safety_flag"
                safe_turn.case_state = current_case
                return safe_turn

            turn.case_state = merge_case_state(current_case, turn.case_state)
            if current_state is ConversationState.EXPERIENCE_MAPPING:
                turn = normalise_experience_mapping_turn(turn)
            elif current_state is ConversationState.RATIONALE_AND_PERMISSION:
                permission_was_already_requested = current_case.reflection_permission_requested
                turn.case_state.reflection_permission_requested = True
                if turn.permission_granted is True:
                    turn.case_state.reflection_permission_granted = True
                elif permission_was_already_requested:
                    turn.message = (
                        "We can leave those reflection questions there."
                        if turn.permission_granted is False
                        else "I have not taken that as permission, so we can leave those reflection questions there."
                    )
                    turn.stage_complete = False
                    turn.next_state = ConversationState.RATIONALE_AND_PERMISSION
            turn.next_state = resolve_state_transition(current_state, turn, turn.case_state)
            turn.summary_card = None
            normalise_validation_plan(turn)
            turn.message = normalise_assistant_message(turn, turn.next_state, history)
            turn.quick_replies = sanitise_quick_replies(turn.quick_replies)

            rejection_reasons = quality_rejection_reasons(
                turn, turn.next_state, history, user_text
            )
            if rejection_reasons and attempt == 0:
                rejection_feedback = "; ".join(rejection_reasons)
                continue
            if rejection_reasons:
                turn = grounded_fallback_turn(
                    turn, turn.next_state, history, user_text
                )
            if deterministic_risk is RiskLevel.ELEVATED and turn.risk_level is RiskLevel.NONE:
                turn.risk_level = RiskLevel.ELEVATED
                turn.risk_reason = reason
            return turn

        raise RuntimeError("The model returned no usable structured output.")

    def create_summary(
        self,
        history: Sequence[MessageRecord],
        case_state: CaseState | None = None,
    ) -> SummaryCard:
        transcript = [
            {
                "role": "user" if item.role.value == "participant" else "assistant",
                "content": item.content,
            }
            for item in history[-40:]
            if item.kind == "chat" and item.role.value in {"participant", "assistant"}
        ]
        payload = {
            "case_state": (case_state or CaseState()).model_dump(mode="json"),
            "conversation": transcript,
        }
        response = self.client.responses.parse(
            model=self.model,
            input=[
                {"role": "developer", "content": SUMMARY_PROMPT},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            text_format=SummaryCard,
            store=False,
            max_output_tokens=1600,
        )
        card = response.output_parsed
        if card is None:
            raise RuntimeError("The model returned no structured reflection card.")
        participant_text = " ".join(
            item.content
            for item in history
            if item.role.value == "participant" and item.kind == "chat"
        )
        card = ensure_possible_interpretations(card, participant_text)
        return ensure_possible_next_steps(card, case_state, participant_text)


class DemoReflectionEngine:
    """Deterministic local flow for UI evaluation without an API key."""

    def __init__(self, crisis_support_text: str = "") -> None:
        self.crisis_support_text = crisis_support_text

    def respond(
        self,
        current_state: ConversationState,
        history: Sequence[MessageRecord],
        user_text: str,
        case_state: CaseState | None = None,
    ) -> AssistantTurn:
        current_case = (case_state or CaseState()).model_copy(deep=True)
        risk, reason = detect_risk(user_text)
        if risk is RiskLevel.IMMINENT:
            turn = crisis_turn(current_state, self.crisis_support_text)
            turn.risk_reason = reason
            turn.case_state = current_case
            return turn
        if is_unsure(user_text):
            return AssistantTurn(
                message=unsure_prompt(current_state),
                next_state=current_state,
                case_state=current_case,
                risk_level=risk,
                risk_reason=reason,
                quick_replies=quick_replies_for_state(current_state),
            )

        if current_state is ConversationState.EXPERIENCE_MAPPING:
            missing = missing_case_slots(current_case)
            if missing:
                name = missing[0]
                setattr(
                    current_case,
                    name,
                    CaseSlot(
                        value=user_text.strip(),
                        source=SlotSource.EXPLICIT_USER_STATEMENT,
                        confidence=0.95,
                        needs_clarification=False,
                    ),
                )
            turn = AssistantTurn(
                message="Stage 3 response is normalised below.",
                next_state=current_state,
                case_state=current_case,
                stage_complete=not missing_case_slots(current_case),
                risk_level=risk,
                risk_reason=reason,
            )
            turn = normalise_experience_mapping_turn(turn)
            turn.next_state = resolve_state_transition(current_state, turn, turn.case_state)
            return turn

        if current_state is ConversationState.RATIONALE_AND_PERMISSION:
            granted = user_text.casefold().strip() in {"yes", "yes, gently", "okay", "ok", "i agree"}
            current_case.reflection_permission_requested = True
            current_case.reflection_permission_granted = granted
            turn = AssistantTurn(
                message=("Permission accepted." if granted else "We can leave those reflection questions there."),
                next_state=(ConversationState.ASSUMPTION_EXAMINATION if granted else current_state),
                case_state=current_case,
                stage_complete=granted,
                permission_granted=granted,
            )
            if granted:
                return grounded_fallback_turn(
                    turn,
                    ConversationState.ASSUMPTION_EXAMINATION,
                    history,
                    user_text,
                )
            return turn

        if current_state is ConversationState.COLLABORATIVE_REAPPRAISAL:
            return AssistantTurn(
                message="We have a basic reflection that keeps more than one possibility open.",
                next_state=current_state,
                case_state=current_case,
                stage_complete=True,
            )

        target = next_state(current_state)
        turn = AssistantTurn(
            message=prompt_for_state(target, seed=user_text),
            next_state=target,
            case_state=current_case,
            stage_complete=True,
            risk_level=risk,
            risk_reason=reason,
            should_offer_feedback=target is ConversationState.FEEDBACK_AND_CLOSURE,
        )
        if target in REFLECTION_STATES:
            return grounded_fallback_turn(turn, target, history, user_text)
        return turn

    def create_summary(
        self,
        history: Sequence[MessageRecord],
        case_state: CaseState | None = None,
    ) -> SummaryCard:
        return build_fallback_summary(history, case_state=case_state)
