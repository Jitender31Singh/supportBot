---
name: supportkb-testing
description: |
  Testing, validation, and quality assurance for TrackoBit Support Assistant. Use this skill when you need to run tests, validate workflows, check code quality, benchmark performance, set up evaluations, or ensure production readiness. Covers unit tests, integration tests, linting, type checking, LangGraph workflow validation, and LangSmith evaluation setup.
compatibility: Python 3.11+, pytest, ruff, mypy
---

# Testing & Quality Assurance for supportKB

## Quick Test Commands

### Run All Tests
```bash
make test
# or: pytest -q
```

### Run Specific Tests
```bash
# Test fault classifier
pytest tests/test_fault_classifier.py -v

# Test vehicle normalisation
pytest tests/ -k "vehicle_normalisation" -v

# Test with coverage
pytest --cov=trackobit_assistant --cov-report=html tests/

# Run tests in specific module
pytest tests/test_session_store.py -v
```

### Code Quality Checks
```bash
# Linting (style & imports)
make lint
# or: ruff check trackobit_assistant ui tests scripts

# Type checking
make typecheck
# or: mypy trackobit_assistant

# All checks together
make lint && make typecheck && make test
```

## Unit Tests Coverage

### Fault Classification (tests/test_fault_classifier.py)
- Rule evaluation for different vehicle types
- Error code → fault category mapping
- Boundary cases (missing rules, unknown types)

**Test**: `pytest tests/test_fault_classifier.py -v`

### Vehicle Normalisation (tests/test_vehicle_normaliser.py)
- Input validation (correct format, invalid characters)
- Normalization (whitespace, case handling)
- Edge cases (null, empty, special characters)

**Test**: `pytest tests/ -k "vehicle_normalisation" -v`

### Command Selector (tests/test_command_selector.py)
- Safe execution conditions
- Command ranking by relevance
- Unavailable command handling

**Test**: `pytest tests/test_command_selector.py -v`

### Session Store (tests/test_session_store.py)
- JSON round-trip (save & load)
- In-memory store contracts
- Thread safety (concurrent access)

**Test**: `pytest tests/test_session_store.py -v`

### Workflow Stack (tests/test_workflow_stack.py)
- Pause/resume frame management
- Stale resume detection
- State consistency

**Test**: `pytest tests/test_workflow_stack.py -v`

## Integration Tests

### LangGraph Greeting Flow (tests/test_graph_greeting.py)
- Full graph invocation
- Node execution order
- State transitions
- Transcript saving

**Test**: `pytest tests/test_graph_greeting.py -v`

### Adapter Contracts
- Session store persistence (JSON, in-memory)
- Vehicle API response handling (mock payload, HTTP)
- Ticket client (logging, HTTP)
- Knowledge base retrieval

**Test**: `pytest tests/ -k "adapter" -v`

## LangSmith Evaluation (Optional)

### Setup Starter Datasets
```bash
python -m evals.langsmith_setup
```

This creates:
- Intent classification dataset (greeting, clarify, query, follow-up)
- Fault category dataset (account, software, hardware, parked)
- With sample conversation examples

### Run Evaluation
```bash
python -m evals.langsmith_evaluate
```

Measures:
- Intent parser agreement with expected intents
- Fault classifier agreement with expected categories
- End-to-end conversation flows

### Configure LangSmith
Set in `.env`:
```dotenv
LANGCHAIN_PROJECT=supportbot
LANGSMITH_API_KEY=your_key
```

## Code Quality Standards

### Ruff Linting Rules
- **E**: PEP 8 errors (indentation, naming, whitespace)
- **F**: PyFlakes (unused imports, undefined names)
- **I**: Import sorting

Ignored:
- **E501**: Line length (configured for 120 chars in pyproject.toml)

**Run**: `make lint`

### MyPy Type Checking
- Python 3.11 target
- Strict checking of untyped defs
- Warn on unused ignores
- Ignore missing imports (third-party packages)

**Run**: `make typecheck`

**Config** (`pyproject.toml`):
```toml
[tool.mypy]
python_version = "3.11"
ignore_missing_imports = true
check_untyped_defs = true
warn_unused_ignores = true
```

## LangGraph Workflow Validation

### Export Graph Diagram
```bash
make graph
# or: python scripts/export_graph.py
```

Output: `docs/graph.md` (visual diagram of workflow)

### Validate Node Registration
Check `graph/registry.py` contains all nodes referenced in `graph/builder.py`

### Test Node Contracts
- Nodes must be async callables
- Input: `AssistantState`
- Output: `AssistantState` (modified)
- All mutations are persisted (state is saved after each node)

## Testing Production Readiness

### Checklist Before Deployment

- [ ] All unit tests pass: `make test`
- [ ] Type checking passes: `make typecheck`
- [ ] Linting passes: `make lint`
- [ ] Graph diagram exports: `make graph`
- [ ] Integration tests pass: `pytest tests/test_graph_*.py -v`
- [ ] LangSmith evaluation is configured (if using tracing)
- [ ] `.env` is configured with real API keys (not `.env.example`)
- [ ] PostgreSQL is configured (if not using JSON storage)
- [ ] Knowledge base articles are loaded
- [ ] Device commands are reviewed and validated
- [ ] Logging is monitored and errors are tracked
- [ ] Rate limits and timeouts are configured
- [ ] Error messages are user-safe (no internal details)

### Load Testing

For production deployments, test:
- Concurrent sessions (multiple users at once)
- Parallel messages (user sends multiple messages quickly)
- Large attachments (8 MB screenshots)
- Long conversations (100+ turns)
- Session resume after restart

### Security Checklist

- [ ] No API keys in code (all in `.env`)
- [ ] No customer secrets in logs (SIM, IMEI, phone numbers)
- [ ] HTTPS enabled for production
- [ ] CSRF protection on UI endpoints
- [ ] Rate limiting on API endpoints
- [ ] Authentication/authorization implemented
- [ ] Session expiration configured
- [ ] Audit logs enabled

## Common Test Patterns

### Mocking External APIs
```python
from unittest.mock import MagicMock, patch

# Mock vehicle API response
mock_vehicle_api = MagicMock()
mock_vehicle_api.fetch_vehicle_info.return_value = {
    "vehicle_number": "ABC123",
    "error_codes": ["E001"],
    "status": "parked"
}

with patch('trackobit_assistant.adapters.vehicle_api.HttpVehicleApiClient', mock_vehicle_api):
    # Test code that calls vehicle API
    pass
```

### Testing LangGraph Nodes
```python
from trackobit_assistant.graph.state import AssistantState
from trackobit_assistant.nodes.intent.intent_parser import intent_parser

async def test_greeting_intent():
    state = AssistantState(
        messages=[HumanMessage(content="Hello!")],
        thread_id="test-1"
    )
    result = await intent_parser(state)
    assert result["intent"] == "greeting"
```

### Testing Session Persistence
```python
from trackobit_assistant.adapters.session_store_json import JsonSessionStore

def test_session_round_trip():
    store = JsonSessionStore()
    
    # Save
    session = SessionData(id="test-1", messages=[...])
    store.save_session(session)
    
    # Load
    loaded = store.get_session("test-1")
    assert loaded.id == "test-1"
    assert loaded.messages == session.messages
```

## Debugging Failing Tests

### Run with Verbose Output
```bash
pytest tests/test_fault_classifier.py -v -s
# -v: verbose, -s: show print statements
```

### Run Single Test Function
```bash
pytest tests/test_vehicle_normaliser.py::test_normalize_vehicle_number -v
```

### Run with Pdb Debugger
```bash
pytest tests/test_fault_classifier.py --pdb
# Drops into debugger on failure
```

### Check Coverage for Specific File
```bash
pytest tests/ --cov=trackobit_assistant.services.fault_rules --cov-report=term-missing
```

Shows which lines aren't covered by tests.

## Continuous Integration (CI)

If setting up CI/CD:

```yaml
# Example: .github/workflows/tests.yml
name: Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - uses: actions/setup-python@v2
        with:
          python-version: 3.11
      - run: pip install -r requirements.txt
      - run: make lint && make typecheck && make test
```

## Performance Benchmarking

### Time a Single Graph Invocation
```python
import time
from trackobit_assistant.graph.runtime import Runtime

async def benchmark_graph():
    runtime = Runtime()
    graph = build_graph(runtime)
    
    state = AssistantState(
        messages=[HumanMessage(content="Hello")],
        thread_id="bench-1"
    )
    
    start = time.time()
    result = await graph.ainvoke(state)
    elapsed = time.time() - start
    
    print(f"Graph execution: {elapsed:.2f}s")
```

### Profile Node Execution
```bash
python -m cProfile -s cumulative scripts/benchmark_graph.py
```

Shows which nodes take the most time.

---

**For detailed test setup and examples, see the tests/ directory in the project.**
