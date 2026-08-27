from __future__ import annotations

import streamlit as st
from dotenv import load_dotenv

from .config import Settings
from .engine import DemoReflectionEngine, ReflectionEngine
from .repository import InMemoryRepository, Repository, SupabaseRepository


load_dotenv()


def get_settings() -> Settings:
    try:
        secrets = st.secrets.to_dict()
    except (FileNotFoundError, AttributeError):
        secrets = {}
    return Settings.from_mapping(secrets)


@st.cache_resource
def get_repository(url: str, key: str, demo_mode: bool) -> Repository:
    if demo_mode:
        return InMemoryRepository()
    return SupabaseRepository(url, key)


@st.cache_resource
def get_engine(api_key: str, model: str, crisis_support_text: str):
    if not api_key:
        return DemoReflectionEngine(crisis_support_text)
    return ReflectionEngine(api_key, model, crisis_support_text=crisis_support_text)


def repository_from_settings(settings: Settings) -> Repository:
    return get_repository(
        settings.supabase_url,
        settings.supabase_service_role_key,
        settings.demo_mode,
    )
