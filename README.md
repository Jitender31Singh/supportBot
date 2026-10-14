# TrackoBit Real-Time Support Assistant

A runnable, session-based support chat starter built from the attached workflow/coding-agent specification. It includes a Streamlit customer-facing chat UI, FastAPI chat/session endpoints, a LangGraph turn-based workflow, file-based session persistence, configurable vehicle API and ticket adapters, a YAML command registry, prompt templates, and basic automated tests.

## 1. What you can run now

- **Chat UI:** clean support workspace with a conversation list, a new-chat action, transcript history, screenshot attachment and workflow status context. The chat uses Server-Sent Events (SSE) to show LangGraph node progress and streams RAG answer tokens from the configured model while they are generated; mock/template-based workflow replies render in small chunks.
- **Per-session continuity:** each message invokes the graph with the same `thread_id`; state and transcript are persisted to `data/sessions/*.json`. LangGraph's in-memory checkpointer accelerates continuity during a process lifetime, while JSON state makes the session restorable after restart. Both JSON and in-memory `SessionStore` adapters implement the same interface.
- **Intent and routing:** greetings, new queries, follow-ups, side questions, pause/resume requests, resolution replies and unclear messages have separate routes.
- **Static questions:** retrieval uses only local `data/knowledge_base/*.md` and `*.txt` files. With no approved documents, it explicitly refuses to guess.
- **Vehicle diagnosis:** asks for a vehicle number only if missing, normalises/validates it, uses a mock payload when no live vehicle API URL is configured, classifies account/software/hardware/parked cases, and guides troubleshooting.
- **Device commands:** sample `Concox V5` YAML registry, safe comparator (no `eval`), ordered command selection, structured screenshot-reading path when a vision model is configured, and text-output fallback.
- **Ticket handoff:** creates a local mock ticket ID and logs a support summary by default. Configure `TICKET_API_URL` and `TICKET_API_KEY` to use the included generic HTTP ticket adapter; adapt its request/response contract to your internal ticket API.
- **Tracing hooks:** configure LangSmith environment variables to trace graph runs. The API tags runs with session, vehicle, device and workflow metadata.

## 2. Start on Windows (venv)

1. Install Python 3.11 or newer.
2. Extract this project folder.
3. Double-click `start_windows.bat`.
4. The script creates `.venv`, installs `requirements.txt`, creates `.env` from `.env.example` if needed, then opens the API and UI in separate terminals.
5. Open **http://localhost:8501** for the chat UI. Open **http://127.0.0.1:8000/docs** for the API Swagger page.

The first dependency installation requires internet access. For a manual setup in PowerShell:

```powershell
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn trackobit_assistant.app.main:app --reload --port 8000
```

In a second PowerShell window, from the same project directory and with the venv activated:

```powershell
streamlit run ui/app.py --server.port 8501
```

Linux/macOS: run `bash start_local.sh`.

## 3. Demo mode vs. real integrations

The initial `.env.example` uses `LLM_PROVIDER=mock`, so the UI and deterministic flows can start without API keys. This mode does **not** perform true model reasoning or interpret image content. For a model-backed experience, edit `.env`:

```dotenv
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=your_key_here
ANTHROPIC_MODEL=claude-sonnet-4-5
ANTHROPIC_VISION_MODEL=claude-sonnet-4-5
```

Then restart the API. Model names are configuration values; use a model enabled for your provider/account. The factory keeps provider-specific code in `llm/factory.py`.

### Vehicle API

If `VEHICLE_API_BASE_URL` is blank, the app uses the mock sample payload from the specification (vehicle number in the response is replaced with the entered value). This is test data, not a live query. Configure `VEHICLE_API_BASE_URL`, `VEHICLE_API_PATH`, and `VEHICLE_API_KEY` for your real endpoint. The adapter expects the response fields shown in the project prompt and preserves the raw payload.

### Ticketing

With `TICKET_API_URL` blank, `LoggingTicketClient` is a mock only: it logs the summary and returns a `TRK-XXXXXXXX` ID. It does not create a Jira, HubSpot or internal support ticket. Set `TICKET_API_URL` and optionally `TICKET_API_KEY` to enable the included generic HTTP adapter. Its default request body is `{summary, reason, metadata}` and its response must include `ticket_id` or `id`; adapt this contract to your authorised endpoint before production.

### Knowledge base / RAG

Place approved Markdown or text support articles in `data/knowledge_base/`. The starter `FileKnowledgeBase` ranks chunks lexically so it works without an embedding API. A `LangChainRetrieverKnowledgeBase` adapter is also included for an already-configured LangChain retriever (for example Chroma or FAISS); inject it in the runtime factory to switch retrieval without changing graph nodes. No real TrackoBit how-to articles were supplied in the DOCX, so the knowledge folder is intentionally empty rather than inventing product instructions.

### Screenshot vision

Attach PNG/JPEG/WEBP screenshots (up to 8 MB). With Anthropic vision configured, the vision model returns a structured schema for fields such as GPS fix, GSM signal, battery voltage and GPRS status. In mock mode, the assistant asks the user to paste the output as text instead of claiming that it read the image.

## 4. Architecture

```text
Streamlit chat UI
  └─ FastAPI /sessions and /messages
      └─ load durable session + transcript
          └─ LangGraph (one invoke per message, thread_id=session_id)
              ├─ intent_parser → greeting / clarify / follow-up / interruption
              ├─ query_classifier → RAG answer OR diagnosis frame
              ├─ symptom_analyzer → ask/validate vehicle number
              ├─ vehicle API → deterministic fault rules + structured LLM on ambiguity
              ├─ account advice / software ticket / level-1 troubleshooting
              ├─ command registry → command → screenshot/text → safe output rules
              ├─ resolution / handoff
              └─ save transcript + state after every turn
```

The graph's conditional routes live in `graph/routes.py`; the graph assembly is `graph/builder.py`; session state is in `graph/state.py`. One node module per responsibility lives under `nodes/`. Business rules are in `services/`; integrations are defined in `ports/` and implemented in `adapters/`. Prompts are editable under `prompts/<node>/v1.md`; `PROMPT_VERSIONS` can select a different version per node without code changes. Customer-facing copy is separated into `templates/messages/*.md.j2` and rendered through `formatters/`.

Export the compiled graph diagram:

```bash
python scripts/export_graph.py
```

It writes `docs/graph.md`.

## 5. API basics

- `GET /health` — backend / adapter status.
- `GET /sessions` — saved sessions.
- `POST /sessions` — create a session.
- `GET /sessions/{session_id}` — transcript and safe state summary.
- `POST /sessions/{session_id}/messages` — send text and optional base64 image data (standard JSON response).
- `POST /sessions/{session_id}/messages/stream` — same request shape; emits SSE `progress`, `answer_chunk`, `complete`, or `error` events for the real-time chat UI.
- `POST /sessions/{session_id}/close` — mark a session closed.

The streaming endpoint emits these event types: `progress` (current graph stage), `answer_chunk` (text to render as it arrives), `answer_reset` (replace partial text after a stream fallback), `complete` (final `MessageResponse` with saved transcript/session state), and `error` (a user-safe error). Keep the standard `/messages` endpoint for clients that prefer a single JSON response.

Example request body:

```json
{
  "message": "My GPS location is not updating",
  "attachment_base64": null,
  "attachment_name": null,
  "attachment_mime_type": null
}
```

## 6. Tests and quality checks

```bash
pytest -q
ruff check trackobit_assistant ui tests scripts
python scripts/export_graph.py
```

The unit tests cover fault rules, vehicle normalisation, retries, safe command conditions, command selection, session-store contracts and workflow-stack helpers. A LangGraph greeting smoke test runs when the full dependencies are installed. Use `python -m evals.langsmith_setup` to create starter LangSmith datasets, then `python -m evals.langsmith_evaluate` to measure heuristic intent and deterministic fault-category agreement.

## 7. Production checklist (do not skip)

This repo is a starting implementation, not a production deployment. Before connecting real customers:

1. Replace JSON storage with a shared durable store (a PostgreSQL adapter stub and suggested schema are included in `docs/postgres_schema.sql`) and use a persistent LangGraph checkpointer when needed. JSON files are for a single local process only.
2. Add authentication, tenant/user access checks, rate limits, CSRF/origin controls for your chosen UI deployment, and retention/redaction rules.
3. Connect the real vehicle endpoint and ticket integration; validate API response contracts and ensure logs do not expose SIM/IMEI or customer secrets.
4. Load reviewed support articles and connect a vector retriever, then add retrieval/source evaluation and prompt-injection defenses.
5. Review device commands with hardware/support owners. Do not run a command against a live device based only on a model suggestion; command definitions and diagnosis are registry/rule driven.
6. Configure provider keys, model access, LangSmith project/secret management, alerting, timeouts and budgets.
7. Add graph-level tests for user retries, parallel issues, mixed screenshot+side-question turns, stale resume, failure modes and ticket handoff against your actual contracts.

## 8. Known starter limits

- RAG text uses provider-level streaming when a model is configured. Deterministic/template-based workflow responses are chunked for display after their graph node completes.
- The local store is suitable for one local developer process, not multiple workers/users in production.
- Mock vehicle lookup returns the documented sample payload for any valid vehicle number.
- Mock mode cannot interpret images; use text output or configure the vision model.
- The DOCX did not provide approved product how-to article content, a live vehicle API endpoint, or ticketing credentials. Those remain configurable integration points instead of fabricated behavior.
