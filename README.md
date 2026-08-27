# Non-Clinical Social Anxiety Reflection Chatbot

## Overview

This repository contains a mobile-first research prototype that supports participants in reflecting on social experiences that remain on their mind after an interaction. The Streamlit application uses a structured, staged conversation to help participants describe what happened, distinguish observations from interpretations, consider uncertainty and possible alternative explanations, and create an optional reflection card.

The prototype is designed to support reflection, coping, and understanding of post-event social experiences. It is not a diagnostic tool, clinical intervention, treatment service, or emergency support service.

## Research Context

The project was developed as part of an MSc Design with Behaviour Science research project. It is intended for supervised research and usability evaluation rather than unsupervised clinical use. Before use with participants, the study team should complete the relevant ethics approval, data-protection review, safeguarding procedures, crisis-resource review, usability testing, and security assessment.

## Main Features

- English-only, mobile-first participant interface with Home, Reflect, Reflections, Support, and Settings views.
- Ten internal conversation states mapped to eight participant-visible stages.
- OpenAI Responses API with Pydantic Structured Outputs and `store=False`.
- Semantic experience mapping across event, response, thought, and emotion fields.
- Explicit permission before reflective questioning begins.
- One main question per turn, with content-sensitive emotional acknowledgement.
- Skip and confirmed end-of-conversation controls.
- Deterministic risk detection and a UK-oriented crisis-support pathway that bypasses ordinary model dialogue when imminent risk is detected.
- Optional reflection cards that participants can edit, regenerate, delete, or save; cards remain drafts until explicitly saved.
- Participant ID and informed consent for live researcher monitoring.
- Password-protected Researcher Dashboard with approximately two-second Supabase refreshes.
- Supabase-backed sessions, messages, feedback, risk flags, and reflection-card storage.
- In-memory demonstration mode when live integrations are unavailable.
- Reduced-motion support and a mobile layout designed around a maximum width of approximately 430 px.

## Technology Stack

- Python 3.11+
- Streamlit
- OpenAI Responses API
- Pydantic Structured Outputs
- Supabase PostgreSQL
- `python-dotenv`
- pytest

## Project Structure

```text
app.py                              # Participant-facing Streamlit application
pages/1_Researcher_Dashboard.py     # Password-protected researcher dashboard
reflection_app/
  config.py                         # Environment and Streamlit secret handling
  engine.py                         # OpenAI and deterministic demo engines
  models.py                         # Pydantic models and conversation states
  prompts.py                        # English conversation and safety prompts
  repository.py                     # Supabase and in-memory repositories
  runtime.py                        # Runtime dependency configuration
  safety.py                         # Deterministic risk detection and crisis pathway
  ui_copy.py                        # Participant-facing interface copy
sql/schema.sql                      # PostgreSQL schema, constraints, indexes, and RLS
tests/                              # Automated unit and Streamlit UI-state tests
.env.example                        # Environment-variable template
requirements.txt                    # Python dependencies
```

## Local Setup

Create and activate a virtual environment, then install the dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Create a local environment file from the tracked template:

```bash
cp .env.example .env
```

Fill in only the values required for the mode you intend to run. Never commit `.env` or place credentials in source code. The repository's `.gitignore` excludes `.env`, `.env.*`, Streamlit secrets, common private-key files, and local virtual environments.

Start the participant application:

```bash
streamlit run app.py
```

The participant application is normally available at `http://localhost:8501/`. The multipage dashboard is available at `http://localhost:8501/Researcher_Dashboard` when launched from the same Streamlit process. It may also be started independently on another port:

```bash
streamlit run pages/1_Researcher_Dashboard.py --server.port 8502
```

### Demonstration Mode

Set `DEMO_MODE=true` to use the in-memory repository. If the Supabase URL or service-role key is absent, the application also falls back to demonstration mode. When no OpenAI API key is configured, it uses the deterministic demo conversation engine. Demonstration data is not persistent and should be used only for interface and workflow evaluation.

## Environment Variables

`.env.example` documents the supported configuration:

| Variable | Required for | Description |
|---|---|---|
| `OPENAI_API_KEY` | Live OpenAI responses | Server-side OpenAI API credential. |
| `OPENAI_MODEL` | Live OpenAI responses | Model used by the Responses API; it must support the required Structured Outputs. |
| `SUPABASE_URL` | Persistent storage | Supabase project URL. |
| `SUPABASE_SERVICE_ROLE_KEY` | Persistent storage | Privileged server-side key; never expose it in browser code, URLs, logs, screenshots, or Git. |
| `RESEARCHER_DASHBOARD_PASSWORD` | Researcher Dashboard | A long, randomly generated password. The dashboard remains unavailable when this value is missing. |
| `DEMO_MODE` | Optional | Set to `true` to force in-memory demonstration mode; use `false` for a fully configured Supabase integration. |
| `CRISIS_SUPPORT_TEXT` | Optional but recommended | Study-approved crisis-support wording. Replace the UK default when recruiting elsewhere. |

Environment variables take precedence over equivalent Streamlit secrets. For hosted environments, configure the same names using the platform's secret-management system rather than committing a local `.env` file.

## Supabase Setup and Data Security

1. Create a new Supabase project.
2. Run [`sql/schema.sql`](sql/schema.sql) once in the Supabase SQL Editor.
3. Add the project URL and service-role key to the local `.env` file or an approved deployment secret store.
4. Set `DEMO_MODE=false`.
5. Restart the applications and verify the integration with a clearly labelled test Participant ID before research use.

The schema defines `sessions`, `messages`, and `feedback` tables together with constraints, indexes, row-level security, and default-deny permissions. The Streamlit server uses the Supabase service-role key; it must never be distributed to participants. A production study should additionally define institutional authentication, least-privilege access, audit logging, key rotation, backup, retention, withdrawal, and deletion procedures.

## Safety and Research Boundaries

The chatbot does not diagnose participants, infer unobserved intentions as facts, promise outcomes, or provide treatment. Its deterministic safety pathway uses UK English and directs immediate danger to 999 or A&E, urgent mental-health needs to NHS 111, and emotional support to Samaritans on 116 123. These resources and the researcher escalation procedure must be reviewed for the participant population and study location before deployment.

Automated keyword and pattern checks are conservative research safeguards; they cannot determine a participant's actual level of risk and do not replace assessment by appropriately trained people.

## Tests

Run the full automated test suite and Python compilation check with:

```bash
pytest -q
python -m compileall app.py pages reflection_app tests
```

The tests cover conversation-state transitions, permission, experience mapping, one-question constraints, safety routing, consent, Participant ID validation, repository behaviour, reflection-card workflows, and participant/Dashboard UI states. Live OpenAI and Supabase integration checks require separately managed test credentials and should use disposable, clearly labelled test records.

## Deployment Notes

The participant entry point is `app.py`. The application can be hosted on Streamlit Community Cloud or an institutionally approved container platform. Configure all credentials through the deployment platform's secret manager. Before deployment, validate the database rules and deletion behaviour in a non-production Supabase project, approve local crisis wording and escalation procedures, confirm data residency and retention requirements, review researcher authentication, and complete mobile end-to-end testing.

## Further Reading

- [OpenAI Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs)
- [NHS urgent mental health support](https://www.nhs.uk/nhs-services/mental-health-services/where-to-get-urgent-help-for-mental-health/)
- [Samaritans contact information](https://www.samaritans.org/how-we-can-help/contact-samaritan/)
