from __future__ import annotations

import re
import threading
import uuid
from abc import ABC, abstractmethod
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from .models import (
    ConversationState,
    FeedbackRecord,
    MessageRecord,
    MessageRole,
    RiskLevel,
    SessionRecord,
    SessionStatus,
)


PARTICIPANT_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{3,64}$")

ALLOWED_MESSAGE_KINDS = frozenset(
    {
        "chat",
        "skip",
        "pause",
        "resume",
        "stop",
        "summary_modified",
        "summary_confirmed",
        "summary_deleted",
    }
)


def validate_message_kind(kind: str) -> str:
    if kind not in ALLOWED_MESSAGE_KINDS:
        allowed = ", ".join(sorted(ALLOWED_MESSAGE_KINDS))
        raise ValueError(f"Unsupported message kind {kind!r}. Allowed kinds: {allowed}.")
    return kind


class Repository(ABC):
    @abstractmethod
    def create_session(self, participant_id: str, consented: bool) -> SessionRecord: ...

    @abstractmethod
    def get_session(self, session_id: str) -> SessionRecord | None: ...

    @abstractmethod
    def list_sessions(self, limit: int = 100) -> list[SessionRecord]: ...

    @abstractmethod
    def update_session(self, session_id: str, **changes: Any) -> SessionRecord: ...

    @abstractmethod
    def add_message(
        self,
        session_id: str,
        role: MessageRole,
        content: str,
        state: ConversationState,
        *,
        kind: str = "chat",
        risk_level: RiskLevel = RiskLevel.NONE,
    ) -> MessageRecord: ...

    @abstractmethod
    def list_messages(self, session_id: str) -> list[MessageRecord]: ...

    @abstractmethod
    def add_feedback(
        self,
        session_id: str,
        helpfulness: int,
        felt_understood: bool,
        comments: str,
    ) -> FeedbackRecord: ...

    @abstractmethod
    def list_feedback(self, session_id: str) -> list[FeedbackRecord]: ...

    @abstractmethod
    def delete_session(self, session_id: str) -> None: ...


def validate_participant_id(participant_id: str) -> str:
    value = participant_id.strip()
    if not PARTICIPANT_ID_PATTERN.fullmatch(value):
        raise ValueError(
            "Participant ID must contain 3–64 letters, numbers, hyphens, or underscores."
        )
    return value


class InMemoryRepository(Repository):
    """Process-local storage for evaluation only; not suitable for research data."""

    def __init__(self) -> None:
        self._sessions: dict[str, SessionRecord] = {}
        self._messages: dict[str, list[MessageRecord]] = {}
        self._feedback: dict[str, list[FeedbackRecord]] = {}
        self._message_id = 0
        self._feedback_id = 0
        self._lock = threading.RLock()

    def create_session(self, participant_id: str, consented: bool) -> SessionRecord:
        if not consented:
            raise ValueError("Live monitoring consent is required.")
        participant_id = validate_participant_id(participant_id)
        now = datetime.now(timezone.utc)
        record = SessionRecord(
            id=str(uuid.uuid4()),
            participant_id=participant_id,
            consented_at=now,
            status=SessionStatus.ACTIVE,
            current_state=ConversationState.OPENING,
            risk_level=RiskLevel.NONE,
            created_at=now,
            updated_at=now,
        )
        with self._lock:
            self._sessions[record.id] = record
            self._messages[record.id] = []
            self._feedback[record.id] = []
        return record.model_copy(deep=True)

    def get_session(self, session_id: str) -> SessionRecord | None:
        with self._lock:
            record = self._sessions.get(session_id)
            return record.model_copy(deep=True) if record else None

    def list_sessions(self, limit: int = 100) -> list[SessionRecord]:
        with self._lock:
            records = sorted(
                self._sessions.values(), key=lambda item: item.updated_at, reverse=True
            )[:limit]
            return [item.model_copy(deep=True) for item in records]

    def update_session(self, session_id: str, **changes: Any) -> SessionRecord:
        with self._lock:
            current = self._sessions.get(session_id)
            if current is None:
                raise KeyError(f"Unknown session: {session_id}")
            payload = current.model_dump()
            payload.update(changes)
            payload["updated_at"] = datetime.now(timezone.utc)
            updated = SessionRecord.model_validate(payload)
            self._sessions[session_id] = updated
            return updated.model_copy(deep=True)

    def add_message(
        self,
        session_id: str,
        role: MessageRole,
        content: str,
        state: ConversationState,
        *,
        kind: str = "chat",
        risk_level: RiskLevel = RiskLevel.NONE,
    ) -> MessageRecord:
        kind = validate_message_kind(kind)
        if not content.strip():
            raise ValueError("Message cannot be empty.")
        with self._lock:
            if session_id not in self._sessions:
                raise KeyError(f"Unknown session: {session_id}")
            self._message_id += 1
            record = MessageRecord(
                id=self._message_id,
                session_id=session_id,
                role=role,
                content=content.strip(),
                state=state,
                kind=kind,
                risk_level=risk_level,
                created_at=datetime.now(timezone.utc),
            )
            self._messages[session_id].append(record)
            self.update_session(session_id)
            return record.model_copy(deep=True)

    def list_messages(self, session_id: str) -> list[MessageRecord]:
        with self._lock:
            return [item.model_copy(deep=True) for item in self._messages.get(session_id, [])]

    def add_feedback(
        self,
        session_id: str,
        helpfulness: int,
        felt_understood: bool,
        comments: str,
    ) -> FeedbackRecord:
        if not 1 <= helpfulness <= 5:
            raise ValueError("Helpfulness must be between 1 and 5.")
        with self._lock:
            if session_id not in self._sessions:
                raise KeyError(f"Unknown session: {session_id}")
            self._feedback_id += 1
            record = FeedbackRecord(
                id=self._feedback_id,
                session_id=session_id,
                helpfulness=helpfulness,
                felt_understood=felt_understood,
                comments=comments.strip(),
                created_at=datetime.now(timezone.utc),
            )
            self._feedback[session_id].append(record)
            return record.model_copy(deep=True)

    def list_feedback(self, session_id: str) -> list[FeedbackRecord]:
        with self._lock:
            return [item.model_copy(deep=True) for item in self._feedback.get(session_id, [])]

    def delete_session(self, session_id: str) -> None:
        with self._lock:
            if session_id not in self._sessions:
                raise KeyError(f"Unknown session: {session_id}")
            del self._sessions[session_id]
            self._messages.pop(session_id, None)
            self._feedback.pop(session_id, None)


class SupabaseRepository(Repository):
    def __init__(self, url: str, service_role_key: str) -> None:
        from supabase import create_client

        self.client = create_client(url, service_role_key)

    @staticmethod
    def _session(row: dict[str, Any]) -> SessionRecord:
        return SessionRecord.model_validate(row)

    @staticmethod
    def _message(row: dict[str, Any]) -> MessageRecord:
        return MessageRecord.model_validate(row)

    @staticmethod
    def _feedback_row(row: dict[str, Any]) -> FeedbackRecord:
        return FeedbackRecord.model_validate(row)

    def create_session(self, participant_id: str, consented: bool) -> SessionRecord:
        if not consented:
            raise ValueError("Live monitoring consent is required.")
        participant_id = validate_participant_id(participant_id)
        data = (
            self.client.table("sessions")
            .insert(
                {
                    "participant_id": participant_id,
                    "status": SessionStatus.ACTIVE.value,
                    "current_state": ConversationState.OPENING.value,
                    "risk_level": RiskLevel.NONE.value,
                }
            )
            .execute()
            .data
        )
        return self._session(data[0])

    def get_session(self, session_id: str) -> SessionRecord | None:
        data = (
            self.client.table("sessions")
            .select("*")
            .eq("id", session_id)
            .limit(1)
            .execute()
            .data
        )
        return self._session(data[0]) if data else None

    def list_sessions(self, limit: int = 100) -> list[SessionRecord]:
        data = (
            self.client.table("sessions")
            .select("*")
            .order("updated_at", desc=True)
            .limit(limit)
            .execute()
            .data
        )
        return [self._session(row) for row in data]

    def update_session(self, session_id: str, **changes: Any) -> SessionRecord:
        payload = deepcopy(changes)
        for key in ("status", "current_state", "risk_level"):
            if hasattr(payload.get(key), "value"):
                payload[key] = payload[key].value
        data = (
            self.client.table("sessions")
            .update(payload)
            .eq("id", session_id)
            .execute()
            .data
        )
        if not data:
            raise KeyError(f"Unknown session: {session_id}")
        return self._session(data[0])

    def add_message(
        self,
        session_id: str,
        role: MessageRole,
        content: str,
        state: ConversationState,
        *,
        kind: str = "chat",
        risk_level: RiskLevel = RiskLevel.NONE,
    ) -> MessageRecord:
        kind = validate_message_kind(kind)
        if not content.strip():
            raise ValueError("Message cannot be empty.")
        data = (
            self.client.table("messages")
            .insert(
                {
                    "session_id": session_id,
                    "role": role.value,
                    "content": content.strip(),
                    "state": state.value,
                    "kind": kind,
                    "risk_level": risk_level.value,
                }
            )
            .execute()
            .data
        )
        return self._message(data[0])

    def list_messages(self, session_id: str) -> list[MessageRecord]:
        data = (
            self.client.table("messages")
            .select("*")
            .eq("session_id", session_id)
            .order("created_at")
            .execute()
            .data
        )
        return [self._message(row) for row in data]

    def add_feedback(
        self,
        session_id: str,
        helpfulness: int,
        felt_understood: bool,
        comments: str,
    ) -> FeedbackRecord:
        data = (
            self.client.table("feedback")
            .insert(
                {
                    "session_id": session_id,
                    "helpfulness": helpfulness,
                    "felt_understood": felt_understood,
                    "comments": comments.strip(),
                }
            )
            .execute()
            .data
        )
        return self._feedback_row(data[0])

    def list_feedback(self, session_id: str) -> list[FeedbackRecord]:
        data = (
            self.client.table("feedback")
            .select("*")
            .eq("session_id", session_id)
            .order("created_at")
            .execute()
            .data
        )
        return [self._feedback_row(row) for row in data]

    def delete_session(self, session_id: str) -> None:
        response = self.client.table("sessions").delete().eq("id", session_id).execute()
        if not response.data:
            raise KeyError(f"Unknown session: {session_id}")
