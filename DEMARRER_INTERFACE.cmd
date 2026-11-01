@echo off
cd /d "%~dp0"
if not exist "data\graph.json" (
  python -X utf8 scripts/init_workspace.py
  if errorlevel 1 (
    pause
    exit /b 1
  )
)
python -X utf8 -m orgkg serve --open-browser
if errorlevel 1 pause
