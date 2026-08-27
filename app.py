from __future__ import annotations

import html
import logging
import uuid

import streamlit as st

from reflection_app.engine import build_fallback_summary
from reflection_app.models import (
    CaseState,
    ConversationState,
    MessageRole,
    RiskLevel,
    SessionStatus,
    SummaryCard,
    next_state,
    visible_stage,
)
from reflection_app.prompts import (
    DEFAULT_STAGE_FOUR_PROMPT,
    prompt_for_state,
    quick_replies_for_state,
    skip_entry_prompt,
)
from reflection_app.runtime import get_engine, get_settings, repository_from_settings
from reflection_app.safety import DEFAULT_CRISIS_SUPPORT
from reflection_app.ui_copy import text


LOGGER = logging.getLogger(__name__)

st.set_page_config(
    page_title="Luma · Reflection",
    page_icon="✦",
    layout="centered",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
    :root {
      --bg: #FAF8FF;
      --primary: #7764A7;
      --primary-light: #E9DFFF;
      --pink: #F7DCEC;
      --blue: #DDF1F6;
      --text: #2F2B3A;
      --secondary: #706A7D;
      --border: rgba(119, 100, 167, .18);
      --glass: rgba(255, 255, 255, .68);
      --shadow: 0 18px 50px rgba(86, 70, 126, .10);
      --message-radius: 20px;
    }
    [data-testid="stHeader"], [data-testid="stToolbar"],
    [data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"],
    #MainMenu, footer { display: none !important; }
    html, body, [data-testid="stAppViewContainer"], .stApp {
      background:
        radial-gradient(circle at 15% 12%, rgba(247, 220, 236, .70), transparent 32%),
        radial-gradient(circle at 88% 24%, rgba(221, 241, 246, .78), transparent 34%),
        radial-gradient(circle at 48% 74%, rgba(233, 223, 255, .58), transparent 38%),
        #FAF8FF !important;
      color: var(--text);
    }
    .stApp { min-height: 100vh; }
    .stMainBlockContainer {
      width: 100%; max-width: 430px !important;
      padding: 1rem 1.05rem calc(11.5rem + env(safe-area-inset-bottom)) !important;
    }
    html, body, p, label, button, input, textarea {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Inter, sans-serif;
      color: var(--text);
    }
    h1, h2, h3, .serif-title {
      font-family: Georgia, "Times New Roman", serif !important;
      letter-spacing: -.025em;
      color: var(--text) !important;
    }
    h1 { font-size: clamp(2.2rem, 10vw, 3.15rem) !important; line-height: 1.03 !important; }
    h2 { font-size: 1.72rem !important; }
    p { line-height: 1.62; }
    .eyebrow { color: var(--primary); font-size: .72rem; font-weight: 750; letter-spacing: .14em; text-transform: uppercase; }
    .muted { color: var(--secondary); font-size: .9rem; }
    .brand { font-family: Georgia, serif; font-size: 1.25rem; font-weight: 700; color: var(--text); letter-spacing: -.03em; }
    .brand-mark { color: var(--primary); margin-right: .32rem; }
    .glass, .st-key-hero_card, .st-key-consent_card, .st-key-support_intro,
    .st-key-support_general, .st-key-settings_privacy, .st-key-settings_data,
    .st-key-end_choice, .st-key-card_choice, .st-key-empty_card,
    [class*="st-key-saved_card_"] {
      background: var(--glass);
      border: 1px solid var(--border);
      box-shadow: var(--shadow);
      backdrop-filter: blur(18px); -webkit-backdrop-filter: blur(18px);
      border-radius: 24px;
      padding: 1.2rem 1.15rem;
      animation: card-in .48s ease both;
    }
    .st-key-hero_card { text-align: center; padding: 1.55rem 1.25rem 1.35rem; }
    .aurora-orb-wrap { display: grid; place-items: center; min-height: 174px; margin: 0 0 .15rem; }
    .aurora-orb {
      width: 152px; height: 152px; border-radius: 50%; position: relative;
      background:
        radial-gradient(circle at 28% 27%, rgba(255,255,255,.95), transparent 20%),
        radial-gradient(circle at 68% 32%, #DDF1F6, transparent 34%),
        radial-gradient(circle at 35% 72%, #F7DCEC, transparent 38%),
        linear-gradient(135deg, #E9DFFF, #F7DCEC 48%, #DDF1F6);
      box-shadow: 0 0 42px rgba(189, 163, 226, .42), 0 18px 45px rgba(119,100,167,.18), inset -12px -12px 30px rgba(119,100,167,.08);
      animation: orb-breathe 6s ease-in-out infinite;
    }
    .aurora-orb::after {
      content: ""; position: absolute; inset: 14%; border-radius: inherit;
      border: 1px solid rgba(255,255,255,.65); filter: blur(.2px);
    }
    @keyframes orb-breathe { 0%,100% { transform: scale(.97) rotate(-2deg); } 50% { transform: scale(1.035) rotate(2deg); } }
    @keyframes card-in { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }
    @media (prefers-reduced-motion: reduce) {
      *, *::before, *::after { animation-duration: .01ms !important; animation-iteration-count: 1 !important; scroll-behavior: auto !important; }
    }
    div[data-testid="stButton"] > button, div[data-testid="stFormSubmitButton"] > button {
      min-height: 44px; border-radius: 999px; border: 1px solid var(--border);
      font-weight: 690; box-shadow: none; transition: transform .18s ease, box-shadow .18s ease;
    }
    div[data-testid="stButton"] > button:hover, div[data-testid="stFormSubmitButton"] > button:hover {
      border-color: rgba(119,100,167,.42); transform: translateY(-1px); box-shadow: 0 8px 20px rgba(84,68,125,.10);
    }
    [data-testid="stBaseButton-primary"], [data-testid="stFormSubmitButton"] button[kind="primary"] {
      color: white !important; border: 0 !important;
      background: linear-gradient(135deg, #8875B6, #6F5C9D) !important;
      box-shadow: 0 10px 24px rgba(119,100,167,.24) !important;
    }
    [data-testid="stBaseButton-primary"] p,
    [data-testid="stFormSubmitButton"] button[kind="primary"] p { color:white !important; }
    [data-testid="stBaseButton-secondary"] { background: rgba(255,255,255,.64) !important; color: var(--primary) !important; }
    [data-testid="stBaseButton-tertiary"] { color: var(--primary) !important; }
    .st-key-back_control button,
    .st-key-back_control button:hover,
    .st-key-back_control button:focus {
      min-height:44px !important; padding:.25rem .1rem !important;
      color:var(--primary) !important; background:transparent !important;
      border:0 !important; border-radius:0 !important; box-shadow:none !important;
      transform:none !important;
    }
    .st-key-back_control button p { color:var(--primary) !important; font-weight:700; }
    .st-key-reflection_header [data-testid="stHorizontalBlock"] {
      position:relative; display:grid !important;
      grid-template-columns:80px minmax(0, 1fr) !important;
      gap:.35rem !important; align-items:center !important;
    }
    .st-key-reflection_header [data-testid="stColumn"] {
      width:auto !important; min-width:0 !important; flex:none !important;
    }
    .st-key-reflection_header [data-testid="stColumn"]:nth-child(2) {
      height:44px !important; min-height:44px !important;
    }
    .st-key-reflection_header .top-title {
      position:absolute; top:0; right:0; bottom:0; left:calc(-80px - .35rem);
      height:44px; min-height:44px; padding:0;
      display:flex; align-items:center; justify-content:center; line-height:1;
      pointer-events:none;
    }
    [data-testid="stTextInput"] input, [data-testid="stTextArea"] textarea {
      color: var(--text) !important; background: rgba(255,255,255,.78) !important;
      border: 1px solid rgba(119,100,167,.22) !important; border-radius: 16px !important;
      caret-color: var(--primary);
    }
    input::placeholder, textarea::placeholder { color: #706A7D !important; opacity: 1 !important; }
    [data-testid="stCheckbox"] label p, [data-testid="stWidgetLabel"] p { color: var(--text) !important; }
    [data-testid="stAlert"] { border-radius: 18px; border: 1px solid var(--border); }
    .stProgress > div > div > div > div { background: linear-gradient(90deg, #D7C7F7, #8F7BBC) !important; }
    .stProgress > div > div { background: rgba(119,100,167,.10) !important; }
    .top-title { text-align:center; font-family: Georgia, serif; font-size: 1.1rem; font-weight: 700; padding-top:.52rem; }
    .st-key-stage_progress {
      position: sticky; top: max(.35rem, env(safe-area-inset-top)); z-index: 990;
      margin: .25rem 0 .8rem;
    }
    .stage-progress-card {
      padding: .7rem .65rem .62rem;
      border: 1px solid rgba(119,100,167,.15); border-radius: 18px;
      background: rgba(250,248,255,.88); box-shadow: 0 8px 24px rgba(80,64,116,.08);
      backdrop-filter: blur(18px); -webkit-backdrop-filter: blur(18px);
    }
    .stage-copy { text-align:center; color:var(--secondary); font-size:.72rem; line-height:1.2; margin:.42rem 0 0; }
    .stage-track { height:5px; overflow:hidden; border-radius:999px; background:rgba(119,100,167,.11); }
    .stage-fill { display:block; height:100%; border-radius:inherit; background:linear-gradient(90deg,#D7C7F7,#7764A7); box-shadow:0 0 10px rgba(119,100,167,.18); transition:width .3s ease; }
    .aurora-message { display:flex; gap:.62rem; align-items:flex-end; margin:.9rem 0; animation:card-in .35s ease both; }
    .aurora-message.user { flex-direction:row-reverse; }
    .line-avatar { width:30px; height:30px; flex:0 0 30px; display:grid; place-items:center; border-radius:50%; border:1px solid var(--border); color:var(--primary); background:rgba(255,255,255,.72); }
    .line-avatar svg { width:16px; height:16px; stroke:currentColor; fill:none; stroke-width:1.7; }
    .bubble { max-width:82%; padding:.78rem .92rem; border-radius:var(--message-radius); line-height:1.55; font-size:.94rem; border:1px solid rgba(119,100,167,.13); box-shadow:0 8px 22px rgba(80,64,116,.06); }
    .assistant .bubble { background:rgba(255,255,255,.72); border-radius:var(--message-radius); }
    .user .bubble { background:linear-gradient(135deg, rgba(233,223,255,.92), rgba(247,220,236,.78)); border-radius:var(--message-radius); }
    .reflection-card {
      position:relative; border-radius:24px; padding:1px; margin:1rem 0 .75rem;
      background:linear-gradient(135deg, rgba(213,188,244,.92), rgba(247,220,236,.9), rgba(191,225,235,.9));
      box-shadow:0 20px 48px rgba(91,72,132,.12); animation:card-in .48s ease both;
    }
    .reflection-card-inner { background:rgba(255,255,255,.82); border-radius:23px; padding:1.2rem; backdrop-filter:blur(16px); }
    .reflection-card h3 { margin:.1rem 0 .2rem; font-size:1.38rem; }
    .reflection-section { padding:.76rem 0; border-top:1px solid rgba(119,100,167,.11); }
    .reflection-label { color:var(--primary); font-size:.7rem; font-weight:800; letter-spacing:.08em; text-transform:uppercase; margin-bottom:.26rem; }
    .reflection-value { color:var(--text); line-height:1.5; font-size:.92rem; white-space:pre-wrap; }
    .saved-pill { display:inline-flex; align-items:center; gap:.3rem; padding:.26rem .58rem; border-radius:999px; background:rgba(221,241,246,.8); color:#426773; font-size:.7rem; font-weight:750; }
    .st-key-summary_actions [data-testid="stHorizontalBlock"] { gap:.35rem; }
    .st-key-summary_actions button { padding:.35rem .25rem !important; font-size:.78rem !important; min-height:39px !important; }
    .st-key-light_controls button { min-height:38px !important; font-size:.82rem; background:transparent !important; }
    .st-key-quick_replies button, .st-key-end_choice button { min-height:38px !important; padding:.3rem .58rem !important; font-size:.79rem; background:rgba(255,255,255,.68) !important; border-radius:var(--message-radius) !important; }
    .st-key-create_reflection_card_choice button {
      min-height:40px !important; padding:.35rem .68rem !important;
      border-radius:var(--message-radius) !important; border:0 !important;
      color:#4F3B7B !important; background:linear-gradient(135deg,#E9DFFF,#F7DCEC) !important;
      box-shadow:0 8px 20px rgba(119,100,167,.12) !important;
    }
    .st-key-create_reflection_card_choice button p {
      color:#4F3B7B !important; opacity:1 !important; visibility:visible !important;
      font-size:.79rem !important; white-space:nowrap !important;
    }
    .st-key-keep_talking_card_choice button, .st-key-card_choice_end button {
      min-height:38px !important; padding:.3rem .58rem !important;
      border-radius:var(--message-radius) !important;
      color:var(--primary) !important; background:rgba(255,255,255,.68) !important;
    }
    .st-key-card_generation_error button {
      min-height:38px !important; border-radius:var(--message-radius) !important;
    }
    .st-key-end_choice [data-testid="stBaseButton-primary"] {
      color:white !important; border:0 !important;
      background:linear-gradient(135deg, #8875B6, #6F5C9D) !important;
      box-shadow:0 10px 24px rgba(119,100,167,.24) !important;
    }
    .st-key-end_choice button p {
      white-space:nowrap !important; overflow:visible !important; text-overflow:clip !important;
    }
    .st-key-end_choice [data-testid="stBaseButton-primary"] p {
      color:white !important; opacity:1 !important; visibility:visible !important;
      position:relative; z-index:1;
    }
    .stBottom { bottom:calc(76px + env(safe-area-inset-bottom)) !important; background:transparent !important; z-index:999 !important; }
    [data-testid="stChatInput"] { max-width:408px; margin:0 auto; }
    [data-testid="stChatInput"] > div {
      background:rgba(255,255,255,.92) !important; border:1px solid rgba(119,100,167,.22) !important;
      border-radius:var(--message-radius) !important; box-shadow:0 14px 36px rgba(70,55,103,.14); backdrop-filter:blur(18px);
    }
    [data-testid="stChatInput"] textarea { color:var(--text) !important; }
    .loading-bubble { min-width:62px; min-height:43px; display:flex; align-items:center; justify-content:center; }
    .loading-icon { width:18px; height:18px; border-radius:50%; border:2px solid rgba(119,100,167,.22); border-top-color:var(--primary); animation:loading-spin .75s linear infinite; }
    @keyframes loading-spin { to { transform:rotate(360deg); } }
    .st-key-bottom_nav {
      position:fixed; z-index:1001; left:50%; transform:translateX(-50%);
      bottom:max(10px, env(safe-area-inset-bottom)); width:min(calc(100vw - 22px), 408px);
      padding:.45rem .5rem; border-radius:22px; background:rgba(255,255,255,.86);
      border:1px solid rgba(119,100,167,.18); box-shadow:0 16px 42px rgba(67,53,96,.16);
      backdrop-filter:blur(22px); -webkit-backdrop-filter:blur(22px);
    }
    .st-key-bottom_nav [data-testid="stHorizontalBlock"] { display:flex !important; flex-wrap:nowrap !important; gap:.25rem; }
    .st-key-bottom_nav [data-testid="stColumn"] { min-width:0 !important; width:25% !important; flex:1 1 0 !important; }
    .st-key-bottom_nav button { border:0 !important; box-shadow:none !important; background:transparent !important; min-height:48px !important; border-radius:16px !important; color:var(--secondary) !important; font-size:.7rem !important; padding:.25rem .1rem !important; }
    .st-key-bottom_nav button { flex-direction:column !important; gap:.08rem !important; line-height:1 !important; }
    .st-key-bottom_nav button span { margin:0 !important; font-size:1.18rem !important; }
    .st-key-bottom_nav button p { margin:0 !important; color:var(--secondary) !important; font-size:.66rem !important; line-height:1.05 !important; white-space:nowrap; }
    .st-key-bottom_nav [data-testid="stBaseButton-primary"] { background:linear-gradient(135deg, rgba(233,223,255,.95), rgba(247,220,236,.78)) !important; color:var(--primary) !important; }
    .st-key-bottom_nav [data-testid="stBaseButton-primary"] p { color:var(--primary) !important; }
    .st-key-bottom_nav button:hover { transform:none !important; background:rgba(233,223,255,.58) !important; }
    .st-key-settings_button button { width:44px !important; min-width:44px; float:right; padding:0 !important; }
    .st-key-settings_button button p { font-size:0 !important; }
    .st-key-settings_button button span { margin:0 !important; }
    .support-icon { width:42px; height:42px; border-radius:15px; display:grid; place-items:center; background:linear-gradient(135deg,var(--primary-light),var(--blue)); color:var(--primary); margin-bottom:.7rem; }
    .support-icon svg { width:21px; height:21px; fill:none; stroke:currentColor; stroke-width:1.7; }
    @media (max-width: 480px) {
      .stMainBlockContainer { padding-left:.9rem !important; padding-right:.9rem !important; }
      .aurora-orb { width:138px; height:138px; }
      .aurora-orb-wrap { min-height:156px; }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

settings = get_settings()
repository = repository_from_settings(settings)
engine = get_engine(settings.openai_api_key, settings.openai_model, settings.crisis_support_text)

if "view" not in st.session_state:
    st.session_state.view = "home"
if st.session_state.view not in {"home", "reflect", "reflections", "support", "settings"}:
    st.session_state.view = "home"


REFLECTION_TRANSIENT_KEYS = (
    "quick_replies",
    "editing_summary",
    "confirm_delete_summary",
    "confirm_delete_data",
    "confirm_exit",
    "case_state",
    "end_choice_mode",
    "end_return_state",
    "card_choice_mode",
    "assistant_error",
    "show_onboarding",
    "input_disabled",
    "pending_end",
    "pending_card_offer",
    "completed",
    "stopped",
    "paused",
    "pending_action",
    "last_processed_action_id",
    "pending_card_generation",
    "card_generation_processing_id",
    "last_card_generation_action_id",
    "card_generation_error",
    "card_generation_choice_recorded",
    "card_generation_attempt",
)


def navigate(view: str) -> None:
    st.session_state.view = view
    st.session_state.confirm_delete_summary = False
    st.rerun()


def safe_text(value: str) -> str:
    return html.escape(value).replace("\n", "<br>")


def text_with_fallback(key: str, fallback: str) -> str:
    try:
        value = text(key).strip()
    except (KeyError, AttributeError):
        return fallback
    return value or fallback


def current_session():
    session_id = st.session_state.get("participant_session_id")
    if not session_id:
        return None
    record = repository.get_session(session_id)
    if record is None:
        st.session_state.pop("participant_session_id", None)
    return record


def clear_reflection_transients() -> None:
    for key in REFLECTION_TRANSIENT_KEYS:
        st.session_state.pop(key, None)


def clear_session_state() -> None:
    clear_reflection_transients()
    st.session_state.pop("participant_session_id", None)


def initialise_new_reflection(session_id: str) -> None:
    clear_reflection_transients()
    st.session_state.participant_session_id = session_id
    set_case_state(CaseState())
    st.session_state.end_choice_mode = False
    st.session_state.card_choice_mode = False
    st.session_state.show_onboarding = False
    st.session_state.view = "reflect"


def get_case_state() -> CaseState:
    value = st.session_state.get("case_state")
    return CaseState.model_validate(value) if value else CaseState()


def set_case_state(value: CaseState) -> None:
    st.session_state.case_state = value.model_dump(mode="json")


def render_top_bar(show_brand: bool = True) -> None:
    left, right = st.columns([5, 1])
    with left:
        if show_brand:
            st.markdown('<div class="brand"><span class="brand-mark">✦</span>Luma</div>', unsafe_allow_html=True)
    with right:
        with st.container(key="settings_button"):
            if st.button(text("settings"), icon=":material/settings:", type="tertiary", help=text("settings"), key=f"settings_{st.session_state.view}"):
                navigate("settings")


def render_bottom_nav() -> None:
    items = [
        ("home", "home", ":material/home:"),
        ("reflect", "reflect", ":material/edit_note:"),
        ("reflections", "reflections", ":material/auto_stories:"),
        ("support", "support", ":material/favorite:"),
    ]
    with st.container(key="bottom_nav"):
        columns = st.columns(4)
        for column, (view, label_key, icon) in zip(columns, items):
            with column:
                if st.button(
                    text(label_key), key=f"nav_{view}", icon=icon,
                    type="primary" if st.session_state.view == view else "tertiary",
                    use_container_width=True,
                ):
                    navigate(view)


def render_home(session) -> None:
    can_continue = session is not None and session.status in {
        SessionStatus.ACTIVE,
        SessionStatus.PAUSED,
    }
    render_top_bar()
    with st.container(key="hero_card"):
        st.markdown('<div class="aurora-orb-wrap"><div class="aurora-orb" aria-hidden="true"></div></div>', unsafe_allow_html=True)
        st.markdown(f'<div class="eyebrow">{safe_text(text("tagline"))}</div>', unsafe_allow_html=True)
        st.markdown(f'<h1>{safe_text(text("welcome"))}</h1>', unsafe_allow_html=True)
        st.markdown(f'<p class="muted">{safe_text(text("home_body"))}</p>', unsafe_allow_html=True)
        if can_continue:
            if st.button(text("continue"), type="primary", use_container_width=True, key="continue_reflection"):
                navigate("reflect")
        elif st.button(text("start"), type="primary", use_container_width=True, key="start_reflection"):
            clear_reflection_transients()
            st.session_state.show_onboarding = True
            st.rerun()

    if not can_continue and st.session_state.get("show_onboarding", False):
        with st.container(key="consent_card"):
            st.subheader(text("consent_title"))
            st.caption(text("consent_body"))
            with st.form("consent_form"):
                participant_id = st.text_input(
                    text("participant_id"), max_chars=64, help=text("participant_help")
                )
                consent = st.checkbox(text("consent"))
                submitted = st.form_submit_button(text("begin"), type="primary", use_container_width=True)
            if submitted:
                if not consent:
                    st.error(text("consent_required"))
                else:
                    try:
                        created = repository.create_session(participant_id, consented=True)
                    except ValueError as exc:
                        st.error(str(exc))
                    else:
                        opening = (
                            "You set the pace here. You can skip or end whenever you want. "
                            + prompt_for_state(ConversationState.OPENING)
                        )
                        repository.add_message(
                            created.id, MessageRole.ASSISTANT, opening, ConversationState.OPENING
                        )
                        initialise_new_reflection(created.id)
                        st.rerun()
    if settings.demo_mode:
        st.markdown(f'<p class="muted" style="text-align:center;margin-top:1rem">{safe_text(text("demo"))}</p>', unsafe_allow_html=True)


ASSISTANT_ICON = """<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3v4M12 17v4M3 12h4M17 12h4M6.4 6.4l2.1 2.1M15.5 15.5l2.1 2.1M17.6 6.4l-2.1 2.1M8.5 15.5l-2.1 2.1"/></svg>"""
USER_ICON = """<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="8" r="3.2"/><path d="M5.8 20c.7-4 2.8-6 6.2-6s5.5 2 6.2 6"/></svg>"""


def message_html(role: MessageRole, content: str) -> str:
    kind = "assistant" if role is MessageRole.ASSISTANT else "user"
    icon = ASSISTANT_ICON if kind == "assistant" else USER_ICON
    return (
        f'<div class="aurora-message {kind}"><div class="line-avatar">{icon}</div>'
        f'<div class="bubble">{safe_text(content)}</div></div>'
    )


def loading_message_html() -> str:
    return (
        f'<div class="aurora-message assistant"><div class="line-avatar">{ASSISTANT_ICON}</div>'
        '<div class="bubble loading-bubble" aria-label="Luma is responding">'
        '<span class="loading-icon" aria-hidden="true"></span></div></div>'
    )


def render_message(role: MessageRole, content: str) -> None:
    st.markdown(message_html(role, content), unsafe_allow_html=True)


def persist_summary(session_id: str, card: SummaryCard | None) -> None:
    repository.update_session(
        session_id,
        summary_card=card.model_dump(mode="json") if card else None,
    )


def summary_html(card: SummaryCard) -> str:
    saved = f'<span class="saved-pill">✓ {safe_text(text("saved"))}</span>' if card.status == "confirmed" else ""
    possibilities = card.alternative_interpretation
    if card.possible_interpretations:
        possibilities = "\n".join(f"• {item}" for item in card.possible_interpretations)
    balanced = card.balanced_reappraisal
    if card.possible_interpretations:
        balanced = (
            "These are possible explanations, not established facts:\n"
            + "\n".join(f"• {item}" for item in card.possible_interpretations)
            + f"\n\n{card.balanced_reappraisal}"
        )
    possible_next_steps = getattr(card, "possible_next_steps", None) or []
    sections = [
        (text("what_happened"), card.situation),
        (text("what_meant"), card.initial_interpretation),
        (text("other"), possibilities),
        (text("balanced"), balanced),
    ]
    if possible_next_steps:
        sections.append(
            (
                text("possible_next_steps"),
                "\n".join(f"• {item}" for item in possible_next_steps),
            )
        )
    body = "".join(
        f'<div class="reflection-section"><div class="reflection-label">{safe_text(label)}</div>'
        f'<div class="reflection-value">{safe_text(value)}</div></div>'
        for label, value in sections
    )
    return (
        '<div class="reflection-card"><div class="reflection-card-inner">'
        f'{saved}<h3>{safe_text(text("draft_title"))}</h3>'
        f'<p class="muted">{safe_text(text("draft_note"))}</p>{body}</div></div>'
    )


def render_summary_card(session, messages, *, controls: bool = True) -> None:
    card = SummaryCard.model_validate(session.summary_card)
    possible_next_steps = getattr(card, "possible_next_steps", None) or []
    if st.session_state.get("editing_summary", False) and controls:
        with st.form("summary_edit_form"):
            situation = st.text_area(text("what_happened"), card.situation)
            meaning = st.text_area(text("what_meant"), card.initial_interpretation)
            alternative = st.text_area(text("other"), card.alternative_interpretation)
            balanced = st.text_area(text("balanced"), card.balanced_reappraisal)
            possible_next_steps_text = st.text_area(
                text("possible_next_steps"),
                "\n".join(possible_next_steps),
            )
            saved_changes = st.form_submit_button(text("save_changes"), type="primary", use_container_width=True)
        if saved_changes:
            updated = card.model_copy(update={
                "situation": situation, "initial_interpretation": meaning,
                "alternative_interpretation": alternative, "balanced_reappraisal": balanced,
                "possible_next_steps": [
                    line.strip().lstrip("•- ").strip()
                    for line in possible_next_steps_text.splitlines()
                    if line.strip()
                ][:2],
                "status": "draft",
            })
            persist_summary(session.id, updated)
            repository.add_message(session.id, MessageRole.SYSTEM, "Participant edited the draft reflection card.", ConversationState.SUMMARY_AND_SUPPORT, kind="summary_modified")
            st.session_state.editing_summary = False
            st.rerun()
        return

    st.markdown(summary_html(card), unsafe_allow_html=True)
    if not controls:
        return
    with st.container(key="summary_actions"):
        edit_col, regen_col = st.columns(2)
        if edit_col.button(text("edit"), key="summary_edit", icon=":material/edit:", use_container_width=True):
            st.session_state.editing_summary = True
            st.rerun()
        if regen_col.button(text("regenerate"), key="summary_regenerate", icon=":material/autorenew:", use_container_width=True):
            try:
                regenerated = engine.create_summary(messages, get_case_state())
            except Exception as exc:
                LOGGER.error("Reflection card regeneration failed: %s", type(exc).__name__)
                regenerated = build_fallback_summary(messages, case_state=get_case_state())
            persist_summary(session.id, regenerated)
            repository.add_message(session.id, MessageRole.SYSTEM, "Participant regenerated the draft reflection card.", ConversationState.SUMMARY_AND_SUPPORT, kind="summary_modified")
            st.rerun()
        delete_col, save_col = st.columns(2)
        if delete_col.button(text("delete"), key="summary_delete", icon=":material/delete_outline:", use_container_width=True):
            st.session_state.confirm_delete_summary = True
            st.rerun()
        if save_col.button(text("save"), key="summary_save", icon=":material/bookmark:", type="primary", use_container_width=True):
            card.status = "confirmed"
            persist_summary(session.id, card)
            repository.add_message(session.id, MessageRole.SYSTEM, "Participant saved the reflection card.", ConversationState.SUMMARY_AND_SUPPORT, kind="summary_confirmed")
            st.toast(text("saved"))
            st.rerun()
    if st.session_state.get("confirm_delete_summary", False):
        st.warning(text("delete_draft"))
        yes, no = st.columns(2)
        if yes.button(text("delete_confirm"), type="primary", use_container_width=True, key="confirm_summary_delete"):
            persist_summary(session.id, None)
            repository.add_message(session.id, MessageRole.SYSTEM, "Participant deleted the reflection card.", ConversationState.SUMMARY_AND_SUPPORT, kind="summary_deleted")
            st.session_state.confirm_delete_summary = False
            st.rerun()
        if no.button(text("cancel"), use_container_width=True, key="cancel_summary_delete"):
            st.session_state.confirm_delete_summary = False
            st.rerun()


def process_user_input(session, user_text: str) -> None:
    if not user_text.strip():
        return
    history = repository.list_messages(session.id)
    repository.add_message(session.id, MessageRole.PARTICIPANT, user_text, session.current_state)
    render_message(MessageRole.PARTICIPANT, user_text)
    assistant_placeholder = st.empty()
    assistant_placeholder.markdown(loading_message_html(), unsafe_allow_html=True)
    try:
        turn = engine.respond(session.current_state, history, user_text, get_case_state())
    except Exception as exc:
        LOGGER.error("Assistant response generation failed: %s", type(exc).__name__)
        friendly_error = text_copy = text("reply_error")
        assistant_placeholder.markdown(
            message_html(MessageRole.ASSISTANT, friendly_error), unsafe_allow_html=True
        )
        st.session_state.assistant_error = text_copy
        return
    set_case_state(turn.case_state)
    risk = RiskLevel.IMMINENT if session.risk_level is RiskLevel.IMMINENT else turn.risk_level
    changes = {"current_state": turn.next_state, "risk_level": risk}
    repository.update_session(session.id, **changes)
    stage_three_transition = (
        session.current_state is ConversationState.EXPERIENCE_MAPPING
        and turn.next_state is ConversationState.RATIONALE_AND_PERMISSION
        and turn.stage_complete
    )
    if stage_three_transition:
        repository.add_message(
            session.id,
            MessageRole.ASSISTANT,
            turn.message,
            ConversationState.EXPERIENCE_MAPPING,
            risk_level=turn.risk_level,
        )
        repository.add_message(
            session.id,
            MessageRole.ASSISTANT,
            DEFAULT_STAGE_FOUR_PROMPT,
            ConversationState.RATIONALE_AND_PERMISSION,
            risk_level=turn.risk_level,
        )
        assistant_placeholder.markdown(
            message_html(MessageRole.ASSISTANT, turn.message)
            + message_html(MessageRole.ASSISTANT, DEFAULT_STAGE_FOUR_PROMPT),
            unsafe_allow_html=True,
        )
        turn.quick_replies = quick_replies_for_state(
            ConversationState.RATIONALE_AND_PERMISSION
        )
    else:
        repository.add_message(
            session.id,
            MessageRole.ASSISTANT,
            turn.message,
            turn.next_state,
            risk_level=turn.risk_level,
        )
        assistant_placeholder.markdown(
            message_html(MessageRole.ASSISTANT, turn.message), unsafe_allow_html=True
        )
    if (
        session.current_state is ConversationState.COLLABORATIVE_REAPPRAISAL
        and turn.stage_complete
        and turn.risk_level is not RiskLevel.IMMINENT
    ):
        st.session_state.card_choice_mode = True
    st.session_state.quick_replies = turn.quick_replies
    st.session_state.pop("assistant_error", None)
    st.rerun()


def skip_action_id(session, messages) -> str:
    last_message_id = str(messages[-1].id) if messages else "none"
    return f"skip:{session.id}:{session.current_state.value}:{last_message_id}"


def queue_skip(session, messages) -> None:
    action_id = skip_action_id(session, messages)
    if st.session_state.get("last_processed_action_id") == action_id:
        return
    pending = st.session_state.get("pending_action")
    if pending and pending.get("id") == action_id:
        return
    st.session_state.pending_action = {
        "id": action_id,
        "kind": "skip",
        "session_id": session.id,
        "from_state": session.current_state.value,
    }
    st.session_state.quick_replies = []
    st.rerun()


def process_pending_skip(session) -> None:
    action = st.session_state.pop("pending_action", None)
    if not action or action.get("kind") != "skip":
        return
    action_id = action.get("id", "")
    if (
        not action_id
        or action.get("session_id") != session.id
        or st.session_state.get("last_processed_action_id") == action_id
    ):
        return
    if action.get("from_state") != session.current_state.value:
        return

    # Claim the action before any database write so a Streamlit rerun cannot replay it.
    st.session_state.last_processed_action_id = action_id
    st.session_state.quick_replies = []
    assistant_placeholder = st.empty()
    assistant_placeholder.markdown(loading_message_html(), unsafe_allow_html=True)
    try:
        repository.add_message(
            session.id,
            MessageRole.SYSTEM,
            "Participant skipped the current stage.",
            session.current_state,
            kind="skip",
        )
        if session.current_state is ConversationState.COLLABORATIVE_REAPPRAISAL:
            st.session_state.card_choice_mode = True
            assistant_placeholder.markdown("", unsafe_allow_html=True)
            st.rerun()

        target = next_state(session.current_state)
        message = skip_entry_prompt(target)
        if target is ConversationState.RATIONALE_AND_PERMISSION:
            case_state = get_case_state()
            case_state.reflection_permission_requested = True
            set_case_state(case_state)
        repository.update_session(session.id, current_state=target)
        repository.add_message(session.id, MessageRole.ASSISTANT, message, target)
    except Exception as exc:
        LOGGER.error("Skip processing failed: %s", type(exc).__name__)
        assistant_placeholder.markdown(
            message_html(MessageRole.ASSISTANT, text("reply_error")),
            unsafe_allow_html=True,
        )
        return

    assistant_placeholder.markdown(
        message_html(MessageRole.ASSISTANT, message), unsafe_allow_html=True
    )
    st.rerun()


def render_stage_progress(state: ConversationState) -> None:
    current = visible_stage(state)
    progress = current / 8 * 100
    with st.container(key="stage_progress"):
        st.markdown(
            '<div class="stage-progress-card">'
            '<div class="stage-track" role="progressbar" '
            f'aria-valuemin="1" aria-valuemax="8" aria-valuenow="{current}">'
            f'<span class="stage-fill" style="width:{progress:.1f}%"></span></div>'
            f'<div class="stage-copy">Stage {current} of 8</div></div>',
            unsafe_allow_html=True,
        )


def begin_end_choice(session) -> None:
    st.session_state.end_choice_mode = True
    st.session_state.end_return_state = session.current_state.value
    st.session_state.card_choice_mode = False
    st.rerun()


def complete_session(session, *, event: str) -> None:
    repository.update_session(session.id, status=SessionStatus.COMPLETED)
    repository.add_message(
        session.id,
        MessageRole.SYSTEM,
        event,
        session.current_state,
        kind="stop",
    )
    st.session_state.end_choice_mode = False
    st.session_state.card_choice_mode = False
    st.rerun()


def queue_reflection_card_generation(session, *, end_after: bool = False) -> None:
    if st.session_state.get("pending_card_generation"):
        return
    if st.session_state.get("card_generation_processing_id"):
        return
    attempt = int(st.session_state.get("card_generation_attempt", 0)) + 1
    st.session_state.card_generation_attempt = attempt
    st.session_state.pending_card_generation = {
        "id": f"card:{session.id}:{attempt}:{uuid.uuid4().hex}",
        "session_id": session.id,
        "end_after": end_after,
    }
    st.session_state.pop("card_generation_error", None)
    st.rerun()


def create_reflection_card(session, action: dict[str, object]) -> None:
    action_id = str(action.get("id", ""))
    end_after = bool(action.get("end_after", False))
    if (
        not action_id
        or action.get("session_id") != session.id
        or st.session_state.get("last_card_generation_action_id") == action_id
    ):
        st.session_state.pop("card_generation_processing_id", None)
        return

    placeholder = st.empty()
    placeholder.markdown(loading_message_html(), unsafe_allow_html=True)
    try:
        choice_key = f"{session.id}:{'end' if end_after else 'stage_six'}"
        recorded = dict(st.session_state.get("card_generation_choice_recorded", {}))
        if not recorded.get(choice_key):
            repository.add_message(
                session.id,
                MessageRole.SYSTEM,
                "Participant explicitly requested a draft reflection card.",
                session.current_state,
                kind="chat",
            )
            recorded[choice_key] = True
            st.session_state.card_generation_choice_recorded = recorded

        messages = repository.list_messages(session.id)
        card = engine.create_summary(messages, get_case_state())
    except Exception as exc:
        LOGGER.error("Reflection card generation failed: %s", type(exc).__name__)
        placeholder.empty()
        st.session_state.pop("card_generation_processing_id", None)
        st.session_state.pop("pending_card_generation", None)
        st.session_state.card_generation_error = {"end_after": end_after}
        st.session_state.end_choice_mode = False
        st.session_state.card_choice_mode = False
        st.rerun()

    try:
        card.status = "draft"
        changes = {
            "summary_card": card.model_dump(mode="json"),
            **(
                {"status": SessionStatus.COMPLETED}
                if end_after
                else {"current_state": ConversationState.SUMMARY_AND_SUPPORT}
            ),
        }
        repository.update_session(session.id, **changes)
    except Exception as exc:
        LOGGER.error("Reflection card persistence failed: %s", type(exc).__name__)
        placeholder.empty()
        st.session_state.pop("card_generation_processing_id", None)
        st.session_state.pop("pending_card_generation", None)
        st.session_state.card_generation_error = {"end_after": end_after}
        st.session_state.end_choice_mode = False
        st.session_state.card_choice_mode = False
        st.rerun()

    st.session_state.last_card_generation_action_id = action_id
    st.session_state.pop("card_generation_processing_id", None)
    st.session_state.pop("pending_card_generation", None)
    st.session_state.pop("card_generation_error", None)
    st.session_state.end_choice_mode = False
    st.session_state.card_choice_mode = False
    placeholder.empty()
    st.rerun()


def process_pending_card_generation(session) -> None:
    action = st.session_state.pop("pending_card_generation", None)
    if not isinstance(action, dict):
        return
    action_id = str(action.get("id", ""))
    if (
        not action_id
        or action.get("session_id") != session.id
        or st.session_state.get("last_card_generation_action_id") == action_id
    ):
        return
    st.session_state.card_generation_processing_id = action_id
    create_reflection_card(session, action)


def render_card_generation_error(session) -> None:
    error_state = st.session_state.get("card_generation_error")
    if not isinstance(error_state, dict):
        return
    with st.container(key="card_generation_error"):
        st.error(text_with_fallback(
            "card_generation_error",
            "We couldn’t create the reflection card just now. Please try again.",
        ))
        if st.button(
            text_with_fallback("try_again", "Try again"),
            type="primary",
            use_container_width=True,
            key="retry_reflection_card_generation",
        ):
            queue_reflection_card_generation(
                session, end_after=bool(error_state.get("end_after", False))
            )
        if st.button(
            text("continue_conversation"),
            use_container_width=True,
            key="continue_after_card_error",
        ):
            st.session_state.pop("card_generation_error", None)
            st.session_state.end_choice_mode = False
            st.session_state.card_choice_mode = False
            st.rerun()
        if st.button(
            text("end_without_card"),
            type="tertiary",
            use_container_width=True,
            key="end_without_card_after_error",
        ):
            st.session_state.pop("card_generation_error", None)
            complete_session(
                session,
                event="Participant ended the conversation without a reflection card.",
            )


def render_end_choice(session) -> None:
    with st.container(key="end_choice"):
        st.write(text("end_card_question"))
        if st.button(
            text_with_fallback("create_card_end", "Create a reflection card"),
            type="primary",
            use_container_width=True,
            key="create_reflection_card_end_choice",
        ):
            queue_reflection_card_generation(session, end_after=True)
        if st.button(text("end_without_card"), use_container_width=True):
            complete_session(session, event="Participant ended the conversation without a reflection card.")
        if st.button(text("continue_conversation"), type="tertiary", use_container_width=True):
            st.session_state.end_choice_mode = False
            st.session_state.card_choice_mode = False
            st.rerun()


def render_card_choice(session) -> None:
    with st.container(key="card_choice"):
        st.write(text("card_choice_question"))
        create_label = text_with_fallback(
            "create_reflection_card", "Create a reflection card"
        )
        if st.button(
            create_label,
            type="primary",
            use_container_width=True,
            key="create_reflection_card_choice",
        ):
            queue_reflection_card_generation(session)
        if st.button(
            text("keep_talking"),
            use_container_width=True,
            key="keep_talking_card_choice",
        ):
            st.session_state.card_choice_mode = False
            st.rerun()
        if st.button(text("end_conversation"), type="tertiary", use_container_width=True, key="card_choice_end"):
            complete_session(session, event="Participant ended after being offered a reflection card.")


def render_feedback(session) -> None:
    if repository.list_feedback(session.id):
        st.success(text("feedback_saved"))
        return
    st.subheader(text("feedback_title"))
    with st.form("feedback_form"):
        helpfulness = st.slider(text("helpful"), 1, 5, 3)
        understood = st.checkbox(text("understood"))
        comments = st.text_area(text("comments"), max_chars=1000)
        submitted = st.form_submit_button(text("submit_finish"), type="primary", use_container_width=True)
    if submitted:
        repository.add_feedback(session.id, helpfulness, understood, comments)
        repository.update_session(session.id, status=SessionStatus.COMPLETED)
        closing = "Thank you for sharing. Take gentle care as you return to your day."
        repository.add_message(session.id, MessageRole.ASSISTANT, closing, ConversationState.FEEDBACK_AND_CLOSURE)
        st.rerun()


def render_reflect(session) -> None:
    if session is None:
        render_top_bar()
        with st.container(key="empty_card"):
            st.subheader(text("reflection"))
            st.write(text("not_started"))
        return
    with st.container(key="reflection_header"):
        back_col, title_col = st.columns([1, 3.4])
        with back_col:
            with st.container(key="back_control"):
                if st.button(text("back"), type="tertiary", key="reflect_back"):
                    navigate("home")
        with title_col:
            st.markdown(f'<div class="top-title">{safe_text(text("reflection"))}</div>', unsafe_allow_html=True)
    if session.status in {SessionStatus.ACTIVE, SessionStatus.PAUSED}:
        render_stage_progress(session.current_state)

    if session.risk_level is RiskLevel.IMMINENT:
        st.error(settings.crisis_support_text or DEFAULT_CRISIS_SUPPORT)

    messages = repository.list_messages(session.id)
    for message in messages:
        if message.kind == "chat" and message.role in {MessageRole.ASSISTANT, MessageRole.PARTICIPANT}:
            render_message(message.role, message.content)

    if session.summary_card:
        render_summary_card(session, messages)

    if session.status is SessionStatus.ACTIVE:
        pending_action = st.session_state.get("pending_action")
        pending_card_generation = st.session_state.get("pending_card_generation")
        card_generation_error = st.session_state.get("card_generation_error")
        end_choice = st.session_state.get("end_choice_mode", False)
        card_choice = st.session_state.get("card_choice_mode", False)
        if pending_card_generation:
            process_pending_card_generation(session)
        elif card_generation_error:
            render_card_generation_error(session)
        elif pending_action:
            process_pending_skip(session)
        elif end_choice:
            render_end_choice(session)
        elif card_choice:
            render_card_choice(session)
        else:
            with st.container(key="light_controls"):
                skip_available = session.current_state not in {
                    ConversationState.RATIONALE_AND_PERMISSION,
                    ConversationState.FEEDBACK_AND_CLOSURE,
                }
                if skip_available:
                    skip_col, end_control = st.columns([1, 2])
                    if skip_col.button(text("skip"), icon=":material/skip_next:", type="tertiary", use_container_width=True):
                        queue_skip(session, messages)
                    if end_control.button(text("end_conversation"), icon=":material/logout:", type="tertiary", use_container_width=True, key="end_conversation_control"):
                        begin_end_choice(session)
                elif st.button(
                    text("end_conversation"), icon=":material/logout:", type="tertiary",
                    use_container_width=True, key="end_conversation_control",
                ):
                    begin_end_choice(session)
            replies = st.session_state.get("quick_replies", [])
            if replies:
                with st.container(key="quick_replies"):
                    columns = st.columns(len(replies))
                    for index, (column, reply) in enumerate(zip(columns, replies)):
                        if column.button(reply, key=f"quick_reply_{index}", use_container_width=True):
                            process_user_input(session, reply)
            if session.current_state is ConversationState.FEEDBACK_AND_CLOSURE:
                render_feedback(session)
            user_text = st.chat_input(text("input"))
            if user_text:
                process_user_input(session, user_text)
    elif session.status is SessionStatus.PAUSED:
        st.info(text("legacy_read_only"))
    elif session.status is SessionStatus.STOPPED:
        st.info(text("stopped"))
    elif session.status is SessionStatus.COMPLETED:
        st.success(text("completed"))


def render_reflections(session) -> None:
    render_top_bar()
    st.markdown(f'<div class="eyebrow">{safe_text(text("reflections"))}</div>', unsafe_allow_html=True)
    st.header(text("reflections"))
    saved = []
    if session is not None:
        for record in repository.list_sessions(limit=100):
            if record.participant_id != session.participant_id or not record.summary_card:
                continue
            card = SummaryCard.model_validate(record.summary_card)
            if card.status == "confirmed":
                saved.append((record, card))
    if not saved:
        with st.container(key="empty_card"):
            st.markdown('<div class="support-icon"><svg viewBox="0 0 24 24"><path d="M5 4h11a3 3 0 0 1 3 3v13H8a3 3 0 0 1-3-3V4Z"/><path d="M8 4v13a3 3 0 0 0 3 3M9 9h6M9 13h5"/></svg></div>', unsafe_allow_html=True)
            st.subheader(text("empty_title"))
            st.write(text("empty_body"))
    for record, card in saved:
        with st.container(key=f"saved_card_{record.id.replace('-', '_')}"):
            st.caption(record.updated_at.strftime("%d %b %Y"))
            st.markdown(summary_html(card), unsafe_allow_html=True)


def render_support() -> None:
    render_top_bar()
    with st.container(key="support_intro"):
        st.markdown('<div class="support-icon"><svg viewBox="0 0 24 24"><path d="M12 21s-7-4.3-7-10.1A4.1 4.1 0 0 1 12 8a4.1 4.1 0 0 1 7 2.9C19 16.7 12 21 12 21Z"/></svg></div>', unsafe_allow_html=True)
        st.header(text("support_title"))
        st.write(text("support_body"))
    with st.container(key="support_general"):
        st.subheader(text("general_support"))
        st.write(text("general_support_body"))
    if st.button(text("urgent_support"), type="primary", use_container_width=True, key="urgent_support_button"):
        st.session_state.show_urgent_support = True
        st.rerun()
    if st.session_state.get("show_urgent_support", False):
        st.error(settings.crisis_support_text or DEFAULT_CRISIS_SUPPORT)


def render_settings(session) -> None:
    back, title = st.columns([1, 4])
    if back.button(text("back"), icon=":material/arrow_back:", type="tertiary", key="settings_back"):
        navigate("home")
    with title:
        st.markdown(f'<div class="top-title" style="text-align:left">{safe_text(text("settings"))}</div>', unsafe_allow_html=True)
    with st.container(key="settings_privacy"):
        st.subheader(text("privacy"))
        st.write(text("privacy_body"))
    with st.container(key="settings_data"):
        st.subheader(text("data_controls"))
        if session is None:
            st.caption(text("not_started"))
        else:
            if st.button(text("delete_data"), icon=":material/delete_forever:", use_container_width=True, key="delete_session_data"):
                st.session_state.confirm_delete_data = True
                st.rerun()
            if st.session_state.get("confirm_delete_data", False):
                st.warning(text("delete_data_warning"))
                yes, no = st.columns(2)
                if yes.button(text("confirm_delete_data"), type="primary", use_container_width=True, key="confirm_delete_data_button"):
                    repository.delete_session(session.id)
                    clear_session_state()
                    st.session_state.view = "home"
                    st.rerun()
                if no.button(text("cancel"), use_container_width=True, key="cancel_delete_data"):
                    st.session_state.confirm_delete_data = False
                    st.rerun()
            st.divider()
            st.write(text("exit_body"))
            if st.button(text("exit_study"), icon=":material/logout:", use_container_width=True, key="exit_study"):
                st.session_state.confirm_exit = True
                st.rerun()
            if st.session_state.get("confirm_exit", False):
                yes, no = st.columns(2)
                if yes.button(text("confirm_exit"), type="primary", use_container_width=True, key="confirm_exit_button"):
                    repository.update_session(session.id, status=SessionStatus.STOPPED)
                    repository.add_message(session.id, MessageRole.SYSTEM, "Participant exited the study session.", session.current_state, kind="stop")
                    st.session_state.confirm_exit = False
                    st.session_state.view = "home"
                    st.rerun()
                if no.button(text("cancel"), use_container_width=True, key="cancel_exit"):
                    st.session_state.confirm_exit = False
                    st.rerun()


session = current_session()
view = st.session_state.view
if view == "home":
    render_home(session)
elif view == "reflect":
    render_reflect(session)
elif view == "reflections":
    render_reflections(session)
elif view == "support":
    render_support()
else:
    render_settings(session)

render_bottom_nav()
