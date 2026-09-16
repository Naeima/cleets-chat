@echo off
REM CLEETS-CHAT: Quick Start Script for Windows
REM Run this after downloading and extracting the package

echo.
echo 🚀 CLEETS-CHAT Quick Start Setup
echo ==================================
echo.

REM Check Python version
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ Python not found. Install from https://www.python.org/
    pause
    exit /b 1
)

for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYTHON_VERSION=%%i
echo ✓ Python version: %PYTHON_VERSION% ^(3.10+ required^)

REM Check for venv
if not exist "venv\" (
    echo 📦 Creating virtual environment...
    python -m venv venv
    echo ✓ Virtual environment created
) else (
    echo ✓ Virtual environment already exists
)

REM Activate venv
echo 🔌 Activating virtual environment...
call venv\Scripts\activate.bat

REM Upgrade pip
echo 📦 Upgrading pip...
python -m pip install --upgrade pip >nul 2>&1

REM Install dependencies
echo 📦 Installing dependencies ^(this may take 1-2 minutes^)...
pip install -r requirements.txt >nul 2>&1
echo ✓ Dependencies installed

REM Check for ANTHROPIC_API_KEY
if "%ANTHROPIC_API_KEY%"=="" (
    echo.
    echo ⚠️  ANTHROPIC_API_KEY not set
    echo.
    echo To enable humanization, set environment variable:
    echo   set ANTHROPIC_API_KEY=sk-ant-your-key-here
    echo.
    echo Get your key at: https://console.anthropic.com
    echo.
) else (
    echo ✓ ANTHROPIC_API_KEY is set
)

REM Test KG files
echo.
echo 📊 Checking knowledge graph files...
if exist "cleets_cskg_enriched.ttl" if exist "cleets_prediction_kg.ttl" (
    echo ✓ Knowledge graphs found
) else (
    echo ⚠️  Knowledge graph files not found
    echo    Expected: cleets_cskg_enriched.ttl, cleets_prediction_kg.ttl
)

echo.
echo ✅ Setup complete!
echo.
echo Next steps:
echo 1. ^(Optional^) Set API key: set ANTHROPIC_API_KEY=sk-ant-...
echo 2. Run dashboard: python app.py
echo 3. Open: http://localhost:8050
echo.
echo Need help? See README.md or QUICK_REFERENCE.md
echo.
pause
