from __future__ import annotations

import hmac
import sys
from pathlib import Path

import streamlit as st


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from reflection_app.models import MessageRole, RiskLevel
from reflection_app.runtime import get_settings, repository_from_settings


st.set_page_config(page_title="Researcher Dashboard", page_icon="🔒", layout="wide")

settings = get_settings()

st.title("Researcher Dashboard")
st.caption("Live read-only conversation monitor · refreshes every 2 seconds")

if not settings.researcher_dashboard_password:
    st.error(
        "Dashboard is disabled because RESEARCHER_DASHBOARD_PASSWORD is not configured."
    )
    st.stop()

if not st.session_state.get("researcher_authenticated", False):
    with st.form("dashboard_login"):
        password = st.text_input("Password", type="password")
        submit = st.form_submit_button("Sign in")
    if submit:
        st.session_state.researcher_authenticated = hmac.compare_digest(
            password, settings.researcher_dashboard_password
        )
        if st.session_state.researcher_authenticated:
            st.rerun()
        st.error("Incorrect password.")
    st.stop()

if st.button("Sign out"):
    st.session_state.researcher_authenticated = False
    st.rerun()

repository = repository_from_settings(settings)


@st.fragment(run_every="2s")
def live_monitor() -> None:
    sessions = repository.list_sessions(limit=100)
    if not sessions:
        st.info("No participant sessions yet.")
        return

    options = {f"{item.participant_id} · {item.status.value} · {item.id[:8]}": item for item in sessions}
    selected_label = st.selectbox("Session", list(options), key="dashboard_session")
    selected = options[selected_label]
    latest = repository.get_session(selected.id) or selected
    messages = repository.list_messages(latest.id)
    feedback = repository.list_feedback(latest.id)

    if latest.risk_level is RiskLevel.IMMINENT:
        st.error("IMMINENT RISK FLAG — follow the approved researcher escalation protocol now.")
    elif latest.risk_level is RiskLevel.ELEVATED:
        st.warning("Elevated risk language flagged for researcher review.")

    a, b, c, d = st.columns(4)
    a.metric("Participant", latest.participant_id)
    b.metric("Status", latest.status.value)
    c.metric("State", latest.current_state.value)
    d.metric("Risk", latest.risk_level.value)
    st.caption(
        f"Consent recorded: {latest.consented_at.isoformat()} · "
        f"Last update: {latest.updated_at.isoformat()}"
    )

    transcript_col, details_col = st.columns([2, 1])
    with transcript_col:
        st.subheader("Conversation")
        for message in messages:
            if message.kind == "chat":
                speaker = (
                    "Participant"
                    if message.role is MessageRole.PARTICIPANT
                    else "Assistant"
                )
                with st.chat_message(
                    "user" if speaker == "Participant" else "assistant"
                ):
                    st.caption(
                        f"{speaker} · {message.state.value} · "
                        f"{message.created_at.strftime('%H:%M:%S')}"
                    )
                    st.write(message.content)
            else:
                st.caption(
                    f"Event: {message.kind} · {message.created_at.strftime('%H:%M:%S')}"
                )
    with details_col:
        st.subheader("Summary card")
        if latest.summary_card:
            st.json(latest.summary_card)
        else:
            st.caption("No summary card.")
        st.subheader("Feedback")
        if feedback:
            for item in feedback:
                st.write(
                    {
                        "helpfulness": item.helpfulness,
                        "felt_understood": item.felt_understood,
                        "comments": item.comments,
                    }
                )
        else:
            st.caption("No feedback submitted.")


live_monitor()
