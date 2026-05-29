@echo off
title GraphRAG System Launcher
echo ===================================================
echo             GRAPHRAG SYSTEM LAUNCHER
echo ===================================================
echo.

echo [1/4] Starting Docker databases (Neo4j ^& Chroma)...
docker compose up -d
if %ERRORLEVEL% neq 0 (
    echo Error: Failed to start Docker compose. Ensure Docker Desktop is running.
    pause
    exit /b %ERRORLEVEL%
)
echo Docker started successfully.
echo.

echo [2/4] Starting Backend API (FastAPI) in a new window...
start "GraphRAG Backend API" cmd /k ".\venv\Scripts\python -m uvicorn visualization.backend.api:app --host 0.0.0.0 --port 8080"

echo [3/4] Starting Frontend Dashboard (Vite) in a new window...
start "GraphRAG Frontend Client" cmd /k "npm run dev --prefix visualization/frontend"

echo [4/4] Starting File Watcher (Incremental Sync) in a new window...
start "GraphRAG File Watcher" cmd /k ".\venv\Scripts\python updater\watcher.py"

echo.
echo ===================================================
echo   All services have been launched!
echo   - FastAPI Backend: http://localhost:8080
echo   - Frontend Dashboard: http://localhost:5173
echo ===================================================
echo.
echo Press any key to exit this launcher window (services will keep running in their own windows).
pause > nul
