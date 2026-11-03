---
name: supportkb-integrations
description: |
  Configuration and integration guide for TrackoBit Support Assistant. Use this skill when setting up external integrations (Vehicle API, Ticket System, Knowledge Base, LLM providers, LangSmith tracing), configuring environment variables, testing API connectivity, or troubleshooting integration issues. Covers all adapters and their configuration options.
compatibility: Python 3.11+, .env configuration, HTTP APIs
---

# Integration Configuration for supportKB

## Overview

supportKB uses a pluggable adapter pattern. All external services are behind protocol interfaces, allowing swappable implementations:

- **Session Storage**: JSON (default), in-memory (dev), PostgreSQL (production)
- **Vehicle API**: HTTP client (default), mock (dev)
- **Ticket System**: HTTP client (default), logging-only (dev)
- **Knowledge Base**: File-based (default), LangChain retriever (optional)
- **LLM Provider**: Mock (dev), Anthropic (default), OpenAI (optional)
- **Tracing**: LangSmith (optional)

## Configuration (.env Setup)

### Quick Start
```bash
# Copy example config
Copy-Item .env.example .env

# Edit .env with your settings
```

### Complete .env Reference

```dotenv
# ===== LLM PROVIDER =====
# mock: No API calls, deterministic responses (dev only)
# anthropic: Claude models (recommended)
# openai: GPT models
LLM_PROVIDER=mock

# For Anthropic
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-sonnet-4-5
ANTHROPIC_VISION_MODEL=claude-sonnet-4-5

# For OpenAI
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4-turbo
OPENAI_VISION_MODEL=gpt-4-vision

# ===== SESSION STORAGE =====
# json: File-based (single process only, dev/demo)
# memory: In-memory (process restarts lose data)
# postgres: PostgreSQL (production)
SESSION_STORE=json
DATA_DIR=./data

# For PostgreSQL
DATABASE_URL=postgresql://user:password@localhost:5432/supportbot

# ===== VEHICLE API =====
# Leave blank to use mock payload (any vehicle number works)
VEHICLE_API_BASE_URL=
VEHICLE_API_PATH=/api/vehicle/{vehicle_number}
VEHICLE_API_KEY=
VEHICLE_API_TIMEOUT=10

# ===== TICKET API =====
# Leave blank to use LoggingTicketClient (mock, logs to file)
TICKET_API_URL=
TICKET_API_KEY=
TICKET_API_TIMEOUT=15

# ===== KNOWLEDGE BASE =====
# Path to directory with .md and .txt support articles
KNOWLEDGE_BASE_PATH=./data/knowledge_base/

# ===== LANGSMITH TRACING (optional) =====
LANGCHAIN_PROJECT=supportbot
LANGSMITH_API_KEY=
LANGSMITH_ENDPOINT=https://api.smith.langchain.com

# ===== PROMPT VERSIONS (optional) =====
# Select specific prompt versions per node (overrides v1.md)
# Format: {"intent_parser": "v2", "query_classifier": "v1"}
PROMPT_VERSIONS=

# ===== LOGGING =====
LOG_LEVEL=INFO
LOG_FILE=./data/assistant.log

# ===== MISC =====
# Port for FastAPI backend
API_PORT=8000

# Port for Streamlit UI
UI_PORT=8501
```

## Session Storage Configuration

### JSON Storage (Development)
Default, single-process only. Files saved to `data/sessions/`:

**Config**:
```dotenv
SESSION_STORE=json
DATA_DIR=./data
```

**Usage**: Suitable for local development and demos. Not for production with multiple workers.

**Files**: Each session is a `.json` file:
```
data/sessions/
├── session-abc123.json
├── session-def456.json
└── ...
```

### In-Memory Storage (Development)
Lost on process restart. Useful for testing:

**Config**:
```dotenv
SESSION_STORE=memory
```

**Usage**: Fastest for testing; not durable.

### PostgreSQL Storage (Production)
Persistent, supports multiple workers:

**Config**:
```dotenv
SESSION_STORE=postgres
DATABASE_URL=postgresql://user:password@localhost:5432/supportbot
```

**Schema**: See `docs/postgres_schema.sql` for the database schema.

**Setup**:
```sql
-- Create database
createdb supportbot

-- Apply schema
psql -U user -d supportbot -f docs/postgres_schema.sql
```

**Verify Connection**:
```bash
python -c "from trackobit_assistant.config.settings import get_settings; s = get_settings(); print(s.database_url)"
```

## LLM Provider Configuration

### Mock Provider (Development)
Deterministic responses. No API calls required.

**Config**:
```dotenv
LLM_PROVIDER=mock
```

**Use Cases**:
- Local development without API keys
- CI/CD testing (deterministic, fast)
- Demos and presentations
- Testing workflow routing without LLM cost

**Limitation**: Cannot interpret images; will ask user to paste text instead.

### Anthropic (Recommended)
Full Claude reasoning and vision capabilities.

**Config**:
```dotenv
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-sonnet-4-5
ANTHROPIC_VISION_MODEL=claude-sonnet-4-5
```

**Available Models**:
- `claude-opus-4-1`: Most capable, higher cost
- `claude-sonnet-4-5`: Balanced (recommended)
- `claude-haiku-3-5`: Fastest, lower cost

**Vision Models**: Same options; use the same model if vision is required.

**Cost Estimation**:
- Sonnet: ~$3/1M input tokens, ~$15/1M output tokens
- Monitor usage via Claude dashboard

### OpenAI (Alternative)
Alternative LLM provider.

**Config**:
```dotenv
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4-turbo
OPENAI_VISION_MODEL=gpt-4-vision
```

**Available Models**:
- `gpt-4-turbo`: Most capable
- `gpt-4`: Balanced
- `gpt-3.5-turbo`: Faster, lower cost

**Limitations**: Vision model is separate; requires fine-tuning for custom tasks.

### Verify LLM Configuration
```bash
python -c "
from trackobit_assistant.llm.factory import create_chat_model
from trackobit_assistant.config.settings import get_settings

settings = get_settings()
llm = create_chat_model(settings)
print(f'Provider: {settings.llm_provider}')
print(f'Model: {llm.model_name}')
"
```

## Vehicle API Integration

### Mock Mode (Development)
Default. Returns template payload for any vehicle number.

**Config**:
```dotenv
VEHICLE_API_BASE_URL=
```

**Response Example**:
```json
{
  "vehicle_number": "ABC123",
  "vehicle_type": "tracker",
  "error_codes": ["E001"],
  "last_gps_time": "2024-01-15T10:30:00Z",
  "status": "active"
}
```

### Real Vehicle API (Production)
Call your actual vehicle API endpoint.

**Config**:
```dotenv
VEHICLE_API_BASE_URL=https://api.trackobit.com
VEHICLE_API_PATH=/v1/vehicle/{vehicle_number}
VEHICLE_API_KEY=your-api-key
VEHICLE_API_TIMEOUT=10
```

**Expected Response Contract**:
```json
{
  "vehicle_number": "string",
  "vehicle_type": "string (tracker|device|etc)",
  "error_codes": ["string"],
  "error_messages": ["string"],
  "last_gps_time": "ISO timestamp",
  "status": "string (active|parked|offline|etc)",
  "gps_location": {"latitude": 0.0, "longitude": 0.0},
  "gsm_signal": "integer (0-31)",
  "battery_voltage": "float (volts)",
  "gprs_status": "string"
}
```

### Test Vehicle API Connection
```python
from trackobit_assistant.adapters.vehicle_api import HttpVehicleApiClient
from trackobit_assistant.config.settings import get_settings

async def test_vehicle_api():
    settings = get_settings()
    api = HttpVehicleApiClient(
        base_url=settings.vehicle_api_base_url,
        api_path=settings.vehicle_api_path,
        api_key=settings.vehicle_api_key
    )
    
    vehicle_info = await api.fetch_vehicle_info("ABC123")
    print(f"Vehicle: {vehicle_info}")

# Run: python test_vehicle_api.py
```

### Troubleshoot Vehicle API

**Issue**: "Connection timeout"
- Check `VEHICLE_API_BASE_URL` is correct
- Verify network connectivity to the API server
- Check `VEHICLE_API_TIMEOUT` is not too short (default 10s)

**Issue**: "401 Unauthorized"
- Verify `VEHICLE_API_KEY` is correct
- Check if API key has expired

**Issue**: "500 Internal Server Error"
- Vehicle API server error
- Check API logs on server side
- Verify request format matches API contract

## Ticket System Integration

### Mock Mode (Development)
Default. Logs tickets to `data/assistant.log`, generates mock ticket ID (`TRK-XXXXXXXX`).

**Config**:
```dotenv
TICKET_API_URL=
```

**Log Output**:
```
[2024-01-15 10:30:00] [INFO] Ticket created: TRK-ABC12345
Summary: User reported GPS not updating
Reason: software
Vehicle: ABC123
```

### Real Ticket API (Production)
Call your ticket system (Jira, HubSpot, internal, etc.).

**Config**:
```dotenv
TICKET_API_URL=https://tickets.yourdomain.com/api/tickets
TICKET_API_KEY=your-api-key
TICKET_API_TIMEOUT=15
```

**Expected Contract**:
- **Request**:
  ```json
  {
    "summary": "string",
    "reason": "string (account|software|hardware|parked)",
    "metadata": {
      "vehicle_number": "string",
      "session_id": "string",
      "user_message": "string"
    }
  }
  ```

- **Response**:
  ```json
  {
    "ticket_id": "string",  // or "id" field
    "status": "created"
  }
  ```

### Test Ticket API Connection
```python
from trackobit_assistant.adapters.ticket_client import HttpTicketClient

async def test_ticket_api():
    client = HttpTicketClient(
        api_url="https://tickets.yourdomain.com/api/tickets",
        api_key="your-key"
    )
    
    ticket = await client.create_ticket(
        summary="Test ticket",
        reason="software",
        metadata={"vehicle": "ABC123"}
    )
    print(f"Ticket: {ticket}")
```

### Adapt to Your Ticket System

Edit `adapters/ticket_client.py` if your API contract differs:

```python
class CustomTicketClient(TicketClient):
    async def create_ticket(self, summary, reason, metadata):
        # Customize request body for your API
        payload = {
            "title": summary,
            "category": reason,
            "vehicle_id": metadata["vehicle_number"],
            # ... your custom fields
        }
        
        response = await self.http_client.post(
            self.api_url,
            json=payload,
            headers={"Authorization": f"Bearer {self.api_key}"}
        )
        
        # Parse your response contract
        return response.json()["ticket_number"]
```

Then inject in `app/main.py`:
```python
ticket_client = CustomTicketClient(...)
```

## Knowledge Base Configuration

### File-Based RAG (Development)
Default. Uses lexical ranking (no embeddings).

**Config**:
```dotenv
KNOWLEDGE_BASE_PATH=./data/knowledge_base/
```

**Setup**:
1. Create directory: `mkdir -p data/knowledge_base/`
2. Add `.md` or `.txt` files: `data/knowledge_base/gps-not-updating.md`
3. Files are auto-loaded on startup

**Format**:
```markdown
# GPS Not Updating

If your GPS location is not updating, try these steps:

1. Check that GPS is enabled in settings
2. Restart the device
3. Wait 2-3 minutes for first fix

If the problem persists, contact support.
```

### LangChain Retriever (Production)
Optional. Integrates with Chroma, FAISS, Pinecone, etc.

**Example: Chroma**:
```python
from langchain_community.vectorstores import Chroma
from trackobit_assistant.adapters.knowledge_base import LangChainRetrieverKnowledgeBase

# In app/main.py:
retriever = Chroma.from_documents(
    documents=...,
    embeddings=...
).as_retriever()

knowledge_base = LangChainRetrieverKnowledgeBase(retriever)
```

Then inject into `Runtime`.

### Test Knowledge Base Retrieval
```bash
python -c "
from trackobit_assistant.adapters.knowledge_base import FileKnowledgeBase

kb = FileKnowledgeBase('./data/knowledge_base/')
results = kb.search('GPS not updating')
for result in results:
    print(result)
"
```

## LangSmith Tracing Configuration

### Setup (Optional)
LangSmith traces all graph invocations for debugging and evaluation.

**Config**:
```dotenv
LANGCHAIN_PROJECT=supportbot
LANGSMITH_API_KEY=your-key
LANGSMITH_ENDPOINT=https://api.smith.langchain.com
```

**Get API Key**:
1. Go to https://smith.langchain.com/
2. Create organization/project
3. Generate API key
4. Paste in `.env`

### View Traces
1. Go to https://smith.langchain.com/
2. Select project: `supportbot`
3. Click "Traces" tab
4. Each graph invocation is a trace with node-by-node breakdown
5. View input/output, timing, errors

### Create Evaluation Datasets
```bash
python -m evals.langsmith_setup
```

Creates datasets:
- `intent_classification`: 20 labeled messages
- `fault_classification`: 20 labeled vehicle issues

### Run Evaluations
```bash
python -m evals.langsmith_evaluate
```

Measures classifier accuracy using LangSmith.

## LLM Cost Tracking

### Monitor Anthropic Spending
- Go to: https://console.anthropic.com/account/billing/overview
- View real-time token usage and costs
- Set up alerts for budget limits

### Estimate Session Cost
```python
# Rough estimates (Sonnet):
# - Short greeting: ~0.01¢
# - Vehicle diagnosis (vehicle API + fault rules): ~0.1¢
# - Long conversation with RAG: ~1¢

# To control costs:
# - Use mock provider in development
# - Set LLM_PROVIDER=mock in tests
# - Implement rate limiting in production
# - Monitor via LangSmith
```

## Troubleshooting Integrations

### Test All Integrations
```bash
python scripts/test_integrations.py
```

This verifies:
- LLM provider connectivity
- Session storage (read/write)
- Vehicle API (if configured)
- Ticket API (if configured)
- Knowledge base (files loaded)
- LangSmith (if configured)

### Check Configuration
```bash
python -c "
from trackobit_assistant.config.settings import get_settings
import json

settings = get_settings()
config = {
    'llm_provider': settings.llm_provider,
    'session_store': settings.session_store,
    'vehicle_api_url': settings.vehicle_api_base_url or '(mock)',
    'ticket_api_url': settings.ticket_api_url or '(mock)',
    'langsmith_enabled': bool(settings.langsmith_api_key)
}
print(json.dumps(config, indent=2))
"
```

### View Application Logs
```bash
tail -f data/assistant.log
```

Shows:
- Node execution times
- API calls and responses
- Errors and warnings
- Session events

---

**For detailed integration examples, see the adapters/ directory in the project.**
