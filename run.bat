@echo off
chcp 65001 >nul
cd /d "%~dp0"

python -c "import pymupdf" 2>nul
if errorlevel 1 python -c "import fitz" 2>nul
if errorlevel 1 (
    echo Installing dependencies...
    python -m pip install -r requirements.txt
)

python main.py %*
if errorlevel 1 pause
