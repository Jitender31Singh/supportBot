# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**TrackoBit Real-Time Support Assistant** is a session-based support chat system that handles customer inquiries through:
- A Streamlit UI for real-time chat with transcript history and screenshot attachments
- A FastAPI backend with streaming responses and session persistence
- A LangGraph workflow that routes messages through intent parsing, classification, diagnosis, and resolution

The system integrates with external APIs for vehicle data retrieval, ticket creation, and device commands. All session state is persisted to disk (with optional PostgreSQL upgrade).

## Common Development Commands

### Setup
```bash
# Windows quick start (creates venv, installs deps, opens both UIs)
start_windows.bat

# Manual setup (PowerShell)
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

### Running the Application
```bash
# Terminal 1: FastAPI backend (port 8000)
make run
# or: uvicorn trackobit_assistant.app.main:app --reload --port 8000

# Terminal 2: Streamlit UI (port 8501)
streamlit run ui/app.py --server.port 8501

# UI is at http://localhost:8501
# API Swagger docs at http://127.0.0.1:8000/docs
```

### Testing & Quality
```bash
make test                 # Run pytest on tests/ directory
make lint                 # Ruff linting (E, F, I rules; ignore E501 line length)
make typecheck            # MyPy static type checking
make graph                # Export LangGraph workflow diagram to docs/graph.md
```

### Single Test Execution
```bash
pytest tests/test_fault_classifier.py -v
pytest tests/ -k "vehicle_normalisation" -v
```

## Architecture & Key Files

### Graph & Workflow (`trackobit_assistant/graph/`)
The system is built on a LangGraph state machine with ~40 specialized nodes:

- **`state.py`**: `AssistantState` dataclass holds conversation thread, transcript, session metadata, vehicle data, and active workflow
- **`builder.py`**: Assembles the graph from the registry; declares START → load_session → intent_parser and all conditional routes
- **`routes.py`**: Routing functions (e.g., `route_intent`, `route_after_query`) determine which node executes next based on state
- **`registry.py`**: Maps node names to handler functions; called by builder
- **`runtime.py`**: Runtime container that holds runtime config, adapters, and LLM instances; injected into node handlers

### Nodes (`trackobit_assistant/nodes/`)
Organized by responsibility; each node is a callable that takes state and returns updated state:

- **Session layer** (`session/`): `load_session`, `save_session` — manage durable persistence
- **Intent layer** (`intent/`): `intent_parser`, `greeting_node`, `clarify_node`, `query_classifier` — classify user intent
- **Intake layer** (`intake/`): `symptom_analyzer`, `ask_vehicle_no`, `validate_vehicle_no`, `fetch_vehicle_info` — gather vehicle data
- **Classification** (`classification/`): `fault_classifier`, `account_advice`, `create_bug_ticket` — categorize issues
- **Diagnosis & troubleshooting**: `fault_diagnosis`, `select_command`, `process_screenshot`, `basic_troubleshooting`
- **Workflow control** (`workflow_control/`): `pause_workflow`, `resume_workflow`, `push_frame`, `resolve_workflow_choice` — manage conversation state and resumption
- **Resolution** (`resolution/`): `resolution_handler`, `close_session` — end the conversation
- **Handoff** (`handoff/`): `human_handoff` — escalate to human support

### Services (`trackobit_assistant/services/`)
Business logic and helpers:

- **`fault_rules.py`**: Dictionary-based fault diagnosis rules (vehicle type, error code → fault category)
- **`vehicle_normaliser.py`**: Validates and normalizes vehicle numbers
- **`command_selector.py`**: Ranks and selects device commands based on diagnosis
- **`output_analyzer.py`**: Parses device command output for diagnostics
- **`prompt_repository.py`**: Loads prompts from `prompts/<node>/v1.md`; supports version selection via `PROMPT_VERSIONS` env var
- **`workflow_stack.py`**: Manages nested workflow frames (e.g., pause/resume context)
- **`conversation_memory.py`**: Tracks message history for context
- **`device_diagnostics.py`**: Structured device health analysis
- **`module_taxonomy.py`**: Vehicle module/subsystem definitions

### Adapters (`trackobit_assistant/adapters/`)
External integrations; implement interfaces from `ports/`:

- **`session_store_json.py`**, `session_store_memory.py`, `session_store_postgres_stub.py`**: Session persistence backends
- **`vehicle_api.py`**: HTTP adapter for vehicle API; returns normalized payload with error codes and state
- **`ticket_client.py`**: `LoggingTicketClient` (mock) and `HttpTicketClient` (real); creates support tickets
- **`command_registry.py`**: Loads device commands from `config/commands/*.yaml`; validates safe execution conditions
- **`knowledge_base.py`**: File-based RAG from `data/knowledge_base/*.md` and `*.txt`; no embeddings required
- **`pinecone_bug_store.py`**: Optional Pinecone integration for bug tracking (stub)
- **`serialization.py`**: JSON encode/decode for transcript and state

### Ports (`trackobit_assistant/ports/`)
- **`interfaces.py`**: Protocol definitions for `SessionStore`, `VehicleApi`, `TicketClient`, `KnowledgeBase`, `CommandRegistry`

### Configuration & Schemas
- **`config/settings.py`**: Pydantic `Settings` model; reads from `.env` (LLM_PROVIDER, API keys, data paths, etc.)
- **`schemas/models.py`**: Pydantic models for `MessageRequest`, `MessageResponse`, `SessionData`, etc.

### Formatters & Templates
- **`formatters/message_renderer.py`**: Renders Jinja2 templates from `templates/messages/*.md.j2` with state context
- **`templates/messages/`**: Customer-facing message templates

### UI & API
- **`ui/app.py`**: Streamlit chat UI; calls `/sessions/{id}/messages/stream` for real-time SSE responses
- **`app/main.py`**: FastAPI app; defines `/sessions`, `/messages`, `/messages/stream`, `/health`, `/close` endpoints
- **`app/streaming.py`**: SSE event formatting and text chunking

### LLM Factory
- **`llm/factory.py`**: Provider-agnostic LLM instantiation; switches between mock, Anthropic, and OpenAI based on `LLM_PROVIDER` env var

## Environment & Configuration

Create `.env` from `.env.example`:

```dotenv
# LLM provider: mock (no API calls), anthropic, or openai
LLM_PROVIDER=mock
ANTHROPIC_API_KEY=your_key
ANTHROPIC_MODEL=claude-sonnet-4-5
ANTHROPIC_VISION_MODEL=claude-sonnet-4-5

# Vehicle API (optional)
VEHICLE_API_BASE_URL=
VEHICLE_API_PATH=/api/vehicle/{vehicle_number}
VEHICLE_API_KEY=

# Ticket API (optional)
TICKET_API_URL=
TICKET_API_KEY=

# Session storage
SESSION_STORE=json  # or memory, postgres (stub only)
DATA_DIR=./data

# LangSmith tracing (optional)
LANGCHAIN_PROJECT=supportbot
LANGSMITH_API_KEY=
```

## Key Design Patterns

### Session Persistence
- Messages are stored in `data/sessions/{session_id}.json`
- LangGraph's in-memory checkpointer accelerates thread continuity; JSON provides durability
- Each graph invocation (per user message) loads the thread, invokes all nodes, then saves

### Conditional Routing
- Routes are declared in `graph/routes.py` and wired in `builder.py`
- Node return values determine the next node; complex logic is in route functions, not nodes
- Workflow frames (pause/resume) use a stack in state; route functions inspect it

### Adapters & Interfaces
- All integrations (vehicle API, tickets, session store, retrieval) are behind protocols in `ports/interfaces.py`
- Implementations in `adapters/` are swappable; inject via `Runtime`
- Mock implementations enable local testing without external APIs

### Prompts & Templates
- Node-specific prompts are in `prompts/{node}/v1.md`; loaded by `PromptRepository`
- `PROMPT_VERSIONS` env var can override versions per node for A/B testing without code changes
- Customer-facing copy is in Jinja2 templates under `templates/messages/`; rendered by `MessageRenderer`

### Vision & Screenshots
- Screenshots (PNG/JPEG/WEBP, up to 8 MB) are uploaded as base64 in `MessageRequest.attachment_base64`
- Vision node (`process_screenshot`) extracts structured fields (GPS, signal, battery, etc.)
- Mock mode falls back to text output

## Testing Strategy

### Unit Tests (`tests/`)
- Fault classifier: rule evaluation, vehicle type inference
- Vehicle normalizer: input validation and formatting
- Command selector: safe condition checks, ranking
- Session store contracts: load/save correctness
- Workflow stack helpers: pause/resume logic

### Integration / Smoke Tests
- LangGraph greeting flow: full graph invocation with mock responses
- Adapter contracts: session persistence round-trips, HTTP mock responses

### Evaluation (Optional)
```bash
python -m evals.langsmith_setup      # Create starter LangSmith datasets
python -m evals.langsmith_evaluate   # Measure intent/fault agreement
```

## Important Notes for Future Work

### Before Production
1. Replace JSON session storage with PostgreSQL (schema stub in `docs/postgres_schema.sql`)
2. Add authentication, rate limits, CSRF protection, session expiration
3. Integrate real vehicle API and validate response contracts; audit logs for SIM/IMEI exposure
4. Load actual support articles and integrate a vector retriever (LangChain adapters provided)
5. Validate device command definitions with hardware/support teams; never send commands based on model suggestion alone
6. Test concurrent message handling, parallel issues, stale resume, and actual integration failure modes

### Known Limitations
- RAG uses lexical ranking; no embeddings by default
- Local session storage only supports one process; not suitable for distributed workers
- Mock vehicle API returns template payload for any valid vehicle number
- Mock mode cannot interpret images
- Streaming chunking happens after nodes complete (not mid-response)

## Skill Usage in This Project

You can now add existing skills to your Claude Code work in this repository using the Skill tool. For example:
- `/code-review` — review diffs for bugs and improvements
- `/dataviz` — create charts or dashboards
- `/simplify` — clean up code without changing behavior
- `/run` — launch the app and test changes in the UI

Simply invoke them in your conversation as needed.
