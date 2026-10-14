@echo off
setlocal
cd /d %~dp0
if not exist .venv\Scripts\python.exe (
  echo Creating Python virtual environment...
  py -3.11 -m venv .venv
  if errorlevel 1 python -m venv .venv
)
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt
if not exist .env copy .env.example .env
start "TrackoBit API" cmd /k "cd /d %~dp0 && .venv\Scripts\python.exe -m uvicorn trackobit_assistant.app.main:app --reload --host 127.0.0.1 --port 8000"
timeout /t 3 >nul
start "TrackoBit UI" cmd /k "cd /d %~dp0 && set UI_API_BASE_URL=http://127.0.0.1:8000 && .venv\Scripts\python.exe -m streamlit run ui/app.py --server.port 8501"
echo.
echo API: http://127.0.0.1:8000/docs
echo UI:  http://localhost:8501
echo Close the two terminal windows to stop the app.
endlocal
