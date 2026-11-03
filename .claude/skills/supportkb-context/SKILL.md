---
name: supportkb-context
description: |
  Comprehensive TrackoBit Support Assistant project context and architecture guide. Use this skill whenever you're working on the supportKB project, need to understand its architecture, set up the development environment, run tests, or integrate external APIs. This skill provides complete project documentation, common development commands, architecture breakdown, configuration details, testing strategies, and implementation guidance for all major components.
compatibility: Python 3.11+, FastAPI, Streamlit, LangGraph
---

# TrackoBit Real-Time Support Assistant - Complete Project Context

## Quick Overview

**TrackoBit Real-Time Support Assistant** is a session-based customer support chat system that intelligently routes inquiries through a LangGraph workflow. It includes:
- **Streamlit chat UI** with transcript history and screenshot attachments
- **FastAPI backend** with streaming responses and session persistence
- **LangGraph workflow** (~40 nodes) for intent parsing, classification, diagnosis, and resolution
- **Pluggable integrations** for vehicle APIs, ticket systems, and knowledge bases
- **Multi-LLM support** (mock, Anthropic, OpenAI)

## Project Goals

1. Provide automated first-line support for hardware/software issues
2. Intelligently diagnose vehicle problems using fault rules and API data
3. Enable escalation to human support when needed
4. Maintain conversation context and session state across restarts
5. Support multiple integrations while keeping code maintainable and testable

## Architecture at a Glance

```
Streamlit UI (http://localhost:8501)
    ↓ (SSE streaming)
FastAPI Backend (http://127.0.0.1:8000)
    ↓ (REST endpoints)
LangGraph Workflow State Machine (~40 nodes)
    ├─ Intent Recognition Layer (greeting, clarify, query classification)
    ├─ Data Collection Layer (vehicle number validation, API fetch)
    ├─ Analysis & Classification (fault diagnosis, rule matching)
    ├─ Action Layer (command selection, troubleshooting, ticketing)
    ├─ Workflow Control (pause/resume, frame management)
    └─ Persistence (JSON or PostgreSQL)
```

## Directory Structure

```
trackobit_assistant/
├── app/                    # FastAPI application
│   ├── main.py            # Entry point, routes, logging
│   └── streaming.py       # SSE formatting and chunking
├── config/
│   └── settings.py        # Pydantic Settings; reads .env
├── graph/                 # LangGraph workflow
│   ├── builder.py         # Assemble graph from registry + routes
│   ├── state.py           # AssistantState dataclass
│   ├── routes.py          # Conditional routing functions
│   ├── registry.py        # Map node names to handlers
│   └── runtime.py         # Runtime container (adapters, LLM)
├── nodes/                 # ~40 handler functions organized by responsibility
│   ├── session/           # load_session, save_session
│   ├── intent/            # intent_parser, greeting, clarify, query_classifier
│   ├── intake/            # symptom_analyzer, ask/validate vehicle_no, fetch_vehicle_info
│   ├── classification/    # fault_classifier, account_advice, create_bug_ticket
│   ├── diagnosis/         # fault_diagnosis, select_command, process_screenshot
│   ├── troubleshooting/   # basic_troubleshooting, check_config, dashboard evidence
│   ├── workflow_control/  # pause/resume, frame management, routing
│   ├── resolution/        # resolution_handler, close_session
│   ├── handoff/           # human_handoff
│   └── knowledge/         # rag_answer, show_device_commands
├── services/              # Business logic
│   ├── fault_rules.py     # Vehicle fault rules (type → category)
│   ├── vehicle_normaliser.py # Validate & normalize vehicle numbers
│   ├── command_selector.py   # Rank device commands
│   ├── prompt_repository.py  # Load prompts from prompts/<node>/v1.md
│   ├── workflow_stack.py  # Pause/resume frame management
│   └── ...
├── adapters/              # External integrations (swappable)
│   ├── session_store_json.py     # JSON persistence
│   ├── session_store_memory.py   # In-memory (dev only)
│   ├── session_store_postgres_stub.py  # PostgreSQL stub
│   ├── vehicle_api.py     # HTTP adapter for vehicle API
│   ├── ticket_client.py   # LoggingTicketClient (mock) & HttpTicketClient
│   ├── command_registry.py # Load device commands from YAML
│   ├── knowledge_base.py  # File-based RAG from data/knowledge_base/
│   └── pinecone_bug_store.py  # Optional Pinecone integration
├── ports/
│   └── interfaces.py      # Protocol definitions (SessionStore, VehicleApi, etc.)
├── formatters/
│   └── message_renderer.py # Jinja2 template rendering
├── llm/
│   └── factory.py         # Provider-agnostic LLM creation (mock/anthropic/openai)
├── schemas/
│   └── models.py          # Pydantic models (MessageRequest, MessageResponse, etc.)
└── ui/
    └── app.py             # Streamlit chat interface

data/
├── knowledge_base/        # Support articles (.md, .txt)
├── sessions/              # Session state JSON files
├── commands/              # Device command YAML registry
└── assistant.log          # Application logs

prompts/
├── intent_parser/v1.md
├── query_classifier/v1.md
├── fault_classifier/v1.md
└── ...                    # One per node, versioned

templates/
└── messages/              # Jinja2 message templates (.md.j2)

tests/                     # Unit & integration tests
evals/                     # Evaluation scripts for LangSmith
docs/
├── graph.md               # Exported LangGraph diagram
└── postgres_schema.sql    # PostgreSQL schema stub
```

## Common Development Commands

### Environment Setup
```bash
# Windows quick start
start_windows.bat

# Manual setup (PowerShell)
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

### Running the Application
```bash
# Terminal 1: FastAPI backend (port 8000, hot-reload)
make run
# or: uvicorn trackobit_assistant.app.main:app --reload --port 8000

# Terminal 2: Streamlit UI (port 8501)
streamlit run ui/app.py --server.port 8501

# Access:
# UI: http://localhost:8501
# API docs: http://127.0.0.1:8000/docs
```

### Testing & Quality
```bash
# Run all tests
make test
# or: pytest -q

# Run specific test
pytest tests/test_fault_classifier.py -v
pytest tests/ -k "vehicle_normalisation" -v

# Linting (E, F, I rules; ignore line-length)
make lint
# or: ruff check trackobit_assistant ui tests scripts

# Type checking
make typecheck
# or: mypy trackobit_assistant

# Export workflow diagram
make graph
# or: python scripts/export_graph.py
# Output: docs/graph.md
```

### LangSmith Evaluation (Optional)
```bash
# Set up starter datasets
python -m evals.langsmith_setup

# Run evaluation
python -m evals.langsmith_evaluate
```

## Configuration (.env)

Copy `.env.example` to `.env` and customize:

```dotenv
# LLM Provider: mock (no API), anthropic, or openai
LLM_PROVIDER=mock
ANTHROPIC_API_KEY=your_key
ANTHROPIC_MODEL=claude-sonnet-4-5
ANTHROPIC_VISION_MODEL=claude-sonnet-4-5

# Vehicle API (optional; uses mock payload if blank)
VEHICLE_API_BASE_URL=
VEHICLE_API_PATH=/api/vehicle/{vehicle_number}
VEHICLE_API_KEY=

# Ticket API (optional; uses LoggingTicketClient if blank)
TICKET_API_URL=
TICKET_API_KEY=

# Session Storage
SESSION_STORE=json  # or: memory, postgres
DATA_DIR=./data

# LangSmith Tracing (optional)
LANGCHAIN_PROJECT=supportbot
LANGSMITH_API_KEY=

# Prompt Versions (optional; selects prompt version per node)
PROMPT_VERSIONS={"intent_parser": "v2", "query_classifier": "v1"}
```

## Key Design Patterns

### Session & State Persistence
- Each user message invokes the graph with `thread_id=session_id`
- Full transcript and state saved to `data/sessions/{session_id}.json` after every turn
- LangGraph's in-memory checkpointer accelerates continuity during process lifetime
- Designed for single-process deployment; upgrade to PostgreSQL for distributed workers

### LangGraph Workflow
- Starts at `load_session`, routes through `intent_parser`, then branches based on intent
- ~40 specialized nodes handle distinct responsibilities (intake, classification, diagnosis, etc.)
- Conditional edges route based on state (e.g., vehicle number present → fetch API, else ask)
- Workflow frames (stack) enable pause/resume without losing context

### Adapter Pattern
- All integrations (vehicle API, tickets, session store, retrieval) behind protocol interfaces in `ports/interfaces.py`
- Implementations in `adapters/` are swappable; inject via `Runtime`
- Mock implementations enable local testing without external APIs

### Prompt & Template Management
- Node-specific prompts in `prompts/<node>/v1.md`; loaded by `PromptRepository`
- `PROMPT_VERSIONS` env var overrides per-node versions without code changes
- Customer-facing copy in Jinja2 templates (`templates/messages/*.md.j2`); rendered by `MessageRenderer`

### Multi-LLM Support
- `llm/factory.py` creates LLM instances based on `LLM_PROVIDER` env var
- Mock mode: deterministic responses (for testing, demos)
- Anthropic: full-featured reasoning and vision
- OpenAI: alternative provider

## API Endpoints

### Session Management
- `GET /health` — Backend status
- `GET /sessions` — List saved sessions
- `POST /sessions` — Create a new session
- `GET /sessions/{session_id}` — Get transcript & safe state summary
- `POST /sessions/{session_id}/close` — Mark session closed

### Messaging
- `POST /sessions/{session_id}/messages` — Send text/image, get JSON response
- `POST /sessions/{session_id}/messages/stream` — Send text/image, get SSE stream

#### Example Request
```json
{
  "message": "My GPS location is not updating",
  "attachment_base64": null,
  "attachment_name": null,
  "attachment_mime_type": null
}
```

#### SSE Event Types
- `progress` — Current graph stage
- `answer_chunk` — Text to render (streamed)
- `answer_reset` — Replace partial text (fallback)
- `complete` — Final `MessageResponse` with saved transcript
- `error` — User-safe error message

## Testing Strategy

### Unit Tests (tests/)
- Fault classifier: rule evaluation, vehicle type inference
- Vehicle normalizer: input validation, formatting
- Command selector: safe conditions, ranking
- Session store: JSON round-trip, in-memory contracts
- Workflow stack: pause/resume logic

### Integration Tests
- LangGraph greeting flow (full graph invocation)
- Adapter contracts (session persistence, HTTP mocks)

### Evaluation (Optional)
- LangSmith datasets for intent/fault classification accuracy

## Important Notes for Production

### Before Going Live
1. **Persistence**: Replace JSON with PostgreSQL (schema in `docs/postgres_schema.sql`)
2. **Security**: Add authentication, rate limits, CSRF protection, session expiration, audit logs
3. **Vehicle API**: Validate real endpoint contract; audit logs for SIM/IMEI exposure
4. **Knowledge Base**: Load reviewed articles; integrate vector retriever (LangChain adapters provided)
5. **Device Commands**: Validate with hardware team; never execute based on model suggestion alone
6. **Error Handling**: Test concurrent messages, parallel issues, stale resume, actual integration failures
7. **LLM & Monitoring**: Configure key management, LangSmith project, alerting, timeouts, budgets

### Known Limitations
- RAG uses lexical ranking; no embeddings by default
- Local JSON storage only supports one process
- Mock vehicle API returns template payload for any vehicle number
- Mock mode cannot interpret images
- Streaming chunks after nodes complete (not mid-response)

## Workflow Overview

### Intent Recognition
- `intent_parser`: Classifies message as greeting, clarify, new query, follow-up, pause/resume, resolution, or unclear
- Routes to appropriate handler (greeting_node, clarify_node, query_classifier, etc.)

### Query Classification
- `query_classifier`: Is this a retrieval query (RAG answer) or a diagnosis query (vehicle issue)?
- Routes to `rag_answer` or `push_frame` (start diagnosis)

### Vehicle Diagnosis Flow
1. `symptom_analyzer` — Ask for vehicle number if missing
2. `validate_vehicle_no` — Normalize and validate format
3. `fetch_vehicle_info` — Call vehicle API (or use mock)
4. `check_config` — Validate configuration state
5. `fault_classifier` — Apply fault rules based on error codes + vehicle type
6. Route to: `account_advice`, `create_bug_ticket`, `basic_troubleshooting`, `select_command`, or escalation

### Device Commands
- `show_device_commands` — List available Concox V5 commands
- `select_command` — Choose command based on diagnosis
- `process_screenshot` — Parse command output (vision or text)
- `analyze_output` — Determine if issue is resolved
- Route to: troubleshooting, resolution, or escalation

### Session Persistence & Workflow Control
- Every node saves transcript/state after execution
- Workflow frames (stack) manage pause/resume context
- Stale resume detection prevents replaying old actions

## File Organization Philosophy

- **One node = one file** under `nodes/<category>/` — clear responsibility
- **Services** hold multi-node business logic (fault rules, vehicle normalisation, etc.)
- **Adapters** are swappable integrations; behind protocols in `ports/`
- **Prompts** are editable in `prompts/<node>/v1.md` — no hardcoding
- **Templates** are Jinja2 in `templates/messages/` — separate UI text from code

## Common Workflows

### Adding a New Node
1. Create file in `nodes/<category>/<new_node>.py`
2. Implement as async callable: `async def <new_node>(state: AssistantState) -> AssistantState`
3. Register in `graph/registry.py`
4. Wire conditional edges in `graph/builder.py`
5. Add prompt template in `prompts/<new_node>/v1.md`

### Integrating a New External API
1. Define protocol in `ports/interfaces.py`
2. Implement adapter in `adapters/<service>.py`
3. Inject into `Runtime` in `app/main.py`
4. Use via dependency injection in nodes

### Modifying Fault Rules
- Edit `data/commands/fault_rules.yaml` or update `services/fault_rules.py`
- Rules are vehicle_type + error_code → fault_category
- Test with: `pytest tests/test_fault_classifier.py`

### Updating Prompts
- Edit `prompts/<node>/v1.md` — no code change needed
- Or use `PROMPT_VERSIONS` env var to A/B test versions
- Prompts are loaded by `PromptRepository`

## Useful Git Workflow

Current branch: `configBranch1`
Main branch: `master`

- Feature branches: `feature/<name>`
- Bug fixes: `fix/<name>`
- Always PR to `master` with tests passing
- Use conventional commits: `feat:`, `fix:`, `test:`, `docs:`, `refactor:`

## Learning Resources

- **LangGraph docs**: https://langchain-ai.github.io/langgraph/
- **FastAPI docs**: https://fastapi.tiangolo.com/
- **Streamlit docs**: https://docs.streamlit.io/
- **LangChain docs**: https://python.langchain.com/
- **Project README**: See README.md for additional setup details
- **CLAUDE.md**: See CLAUDE.md for developer guide

---

**Need help?** Refer back to the relevant section above, or check the project README and CLAUDE.md for more details.
