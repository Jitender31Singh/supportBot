#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [[ ! -x .venv/bin/python ]]; then python3.11 -m venv .venv || python3 -m venv .venv; fi
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
[[ -f .env ]] || cp .env.example .env
.venv/bin/python -m uvicorn trackobit_assistant.app.main:app --reload --host 127.0.0.1 --port 8000 &
API_PID=$!
trap 'kill "$API_PID" 2>/dev/null || true' EXIT
sleep 3
UI_API_BASE_URL=http://127.0.0.1:8000 .venv/bin/python -m streamlit run ui/app.py --server.port 8501
