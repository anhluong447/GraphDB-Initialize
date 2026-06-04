@echo off
title GraphRAG System Launcher
echo ===================================================
echo             GRAPHRAG SYSTEM LAUNCHER
echo ===================================================
echo.

:: 1. Detect Python Executable Path
set PYTHON_CMD=python
if exist ".\.venv\Scripts\python.exe" (
    set PYTHON_CMD=".\.venv\Scripts\python.exe"
    echo [GraphRAG] Using local .venv python.
) else if exist ".\venv\Scripts\python.exe" (
    set PYTHON_CMD=".\venv\Scripts\python.exe"
    echo [GraphRAG] Using local venv python.
) else if exist "..\.venv\Scripts\python.exe" (
    set PYTHON_CMD="..\.venv\Scripts\python.exe"
    echo [GraphRAG] Using parent .venv python.
) else if exist "..\venv\Scripts\python.exe" (
    set PYTHON_CMD="..\venv\Scripts\python.exe"
    echo [GraphRAG] Using parent venv python.
) else (
    echo [GraphRAG] Warning: Virtual environment not found. Falling back to system 'python'.
)

:: 2. Check and Start Docker databases (using Python config helper to bind correct volumes)
echo [1/4] Starting Docker databases (Neo4j ^& Chroma)...
%PYTHON_CMD% -c "import os, sys; sys.path.append(os.getcwd()); import initialize_graph; initialize_graph._start_docker()"
if %ERRORLEVEL% neq 0 (
    echo Error: Failed to start Docker databases.
    pause
    exit /b %ERRORLEVEL%
)
echo Docker started successfully.
echo.

:: 3. Start Backend API
echo [2/4] Starting Backend API (FastAPI) in a new window...
start "GraphRAG Backend API" cmd /k "%PYTHON_CMD% -m uvicorn visualization.backend.api:app --host 0.0.0.0 --port 8080"

:: 4. Install Frontend Dependencies and Start Frontend Client
echo [3/4] Starting Frontend Dashboard (Vite) in a new window...
if not exist "visualization\frontend\node_modules" (
    echo [GraphRAG] Frontend dependencies not found. Installing node_modules...
    pushd visualization\frontend
    call npm install
    popd
)
start "GraphRAG Frontend Client" cmd /k "npm run dev --prefix visualization/frontend"

:: 5. Start Watcher
echo [4/4] Starting File Watcher (Incremental Sync) in a new window...
start "GraphRAG File Watcher" cmd /k "%PYTHON_CMD% updater\watcher.py"

:: 6. Automatically open web dashboard in default browser
timeout /t 3 > nul
echo Opening browser dashboard...
start http://localhost:5173

echo.
echo ===================================================
echo   All services have been launched!
echo   - FastAPI Backend: http://localhost:8080
echo   - Frontend Dashboard: http://localhost:5173
echo ===================================================
echo.
echo Press any key to exit this launcher window (services will keep running in their own windows).
pause > nul
