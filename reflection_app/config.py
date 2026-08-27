from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Mapping


def _read(source: Mapping[str, Any], key: str, default: str = "") -> str:
    value = os.getenv(key)
    if value is None:
        value = source.get(key, default)
    return str(value).strip() if value is not None else default


@dataclass(frozen=True)
class Settings:
    openai_api_key: str
    openai_model: str
    supabase_url: str
    supabase_service_role_key: str
    researcher_dashboard_password: str
    crisis_support_text: str
    demo_mode: bool

    @classmethod
    def from_mapping(cls, source: Mapping[str, Any] | None = None) -> "Settings":
        source = source or {}
        supabase_url = _read(source, "SUPABASE_URL")
        supabase_key = _read(source, "SUPABASE_SERVICE_ROLE_KEY")
        requested_demo = _read(source, "DEMO_MODE", "false").lower() in {
            "1",
            "true",
            "yes",
        }
        return cls(
            openai_api_key=_read(source, "OPENAI_API_KEY"),
            openai_model=_read(source, "OPENAI_MODEL", "gpt-5-mini"),
            supabase_url=supabase_url,
            supabase_service_role_key=supabase_key,
            researcher_dashboard_password=_read(
                source, "RESEARCHER_DASHBOARD_PASSWORD"
            ),
            crisis_support_text=_read(source, "CRISIS_SUPPORT_TEXT"),
            demo_mode=requested_demo or not (supabase_url and supabase_key),
        )
