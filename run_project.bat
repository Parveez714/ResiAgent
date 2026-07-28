@echo off
echo ==============================================
echo Starting Project Analytics Dashboard
echo ==============================================

:: Start Backend
echo Starting FastAPI Backend on http://localhost:8000...
start cmd /k "cd backend && uvicorn main:app --reload --port 8000"

:: Start Frontend
echo Starting React Vite Frontend...
start cmd /k "cd frontend && npm run dev"

echo Both services are starting. Check the opened terminal windows.
echo Backend API docs available at: http://localhost:8000/docs
pause
