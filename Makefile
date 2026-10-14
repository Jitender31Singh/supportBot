.PHONY: run test lint typecheck graph
run:
	uvicorn trackobit_assistant.app.main:app --reload --port 8000

test:
	pytest -q

lint:
	ruff check trackobit_assistant ui tests scripts

typecheck:
	mypy trackobit_assistant

graph:
	python scripts/export_graph.py
