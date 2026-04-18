@echo off
title Stock Management System
color 0A

cd /d "%~dp0"

echo ========================================
echo    STOCK MANAGEMENT SYSTEM
echo ========================================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed!
    echo Please install Python from https://python.org
    pause
    exit /b 1
)

:: Activate virtual environment if exists
if exist "venv\Scripts\activate" (
    echo Activating virtual environment...
    call venv\Scripts\activate
)

:: Install requirements if needed
echo Checking requirements...
pip show Flask >nul 2>&1
if errorlevel 1 (
    echo Installing required packages...
    pip install -r requirements.txt
)

:: Kill any existing server on port 5000
echo Cleaning up previous session...
for /f "tokens=5" %%a in ('netstat -aon ^| find ":5000" ^| find "LISTENING"') do (
    taskkill /f /pid %%a >nul 2>&1
)
timeout /t 1 /nobreak >nul

:: Start the Flask server
echo Starting server...
start "Stock System Server" /min cmd /c "call venv\Scripts\activate && python app.py"

:: Wait for server to start
echo Waiting for server...
timeout /t 5 /nobreak >nul

:: Open browser
echo Opening browser...
start http://localhost:5000

echo.
echo ========================================
echo    SYSTEM IS RUNNING
echo ========================================
echo.
echo The system is ready at: http://localhost:5000
echo.
echo Close this window to STOP the server
echo Or press any key to stop now...
echo.

:: Wait for user to press any key or close window
pause >nul

:: Stop the server when user exits
echo.
echo Shutting down server...
for /f "tokens=5" %%a in ('netstat -aon ^| find ":5000" ^| find "LISTENING"') do (
    taskkill /f /pid %%a >nul 2>&1
)

:: Kill the specific Python process window
taskkill /f /fi "WINDOWTITLE eq Stock System Server" >nul 2>&1

echo.
echo Server stopped successfully!
echo.
timeout /t 2 /nobreak >nul
exit