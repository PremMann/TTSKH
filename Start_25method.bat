@echo off
rem Windows launcher for 25method (same as Start_25method.command on a Mac).
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

if exist ".venv\Scripts\python.exe" (
  set "RUNNER=.venv\Scripts\python.exe"
) else (
  where py >nul 2>nul && (set "RUNNER=py -3") || (set "RUNNER=python")
)

%RUNNER% -c "import numpy, soundfile, PIL, edge_tts, rapidocr_onnxruntime" 2>nul
if errorlevel 1 (
  echo Dependencies are missing. Run Setup_Windows.bat first, or see README.md, Setup on Windows.
  pause
  exit /b 1
)

%RUNNER% -X utf8 -u run.py serve --open-browser
echo Server stopped.
pause
