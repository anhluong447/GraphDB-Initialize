@echo off
title GraphRAG Knowledge Base Server
echo ===================================================
echo       GRAPHRAG KNOWLEDGE BASE SERVER
echo ===================================================
echo.

:: Detect Python executable
set PYTHON_CMD=python
if exist ".\venv\Scripts\python.exe" (
    set PYTHON_CMD=".\venv\Scripts\python.exe"
    echo [Server] Using local venv python.
) else (
    echo [Server] Warning: Virtual environment not found. Using system python.
)

:: Start the server (pass through any arguments like --port 9090)
%PYTHON_CMD% start_server.py %*
