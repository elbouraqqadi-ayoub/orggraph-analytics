@echo off
cd /d "%~dp0"
if not exist "data\graph.json" (
  python -X utf8 -m orgkg ingest
  if errorlevel 1 (
    pause
    exit /b 1
  )
)
python -X utf8 -m orgkg gui
if errorlevel 1 pause
