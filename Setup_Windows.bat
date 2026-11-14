@echo off
rem One-time setup on Windows: creates .venv and installs the Python packages.
cd /d "%~dp0"
set PYTHONUTF8=1

set "PY=python"
where py >nul 2>nul && set "PY=py -3"

if not exist ".venv\Scripts\python.exe" (
  echo Creating .venv ...
  %PY% -m venv .venv
  if errorlevel 1 (
    echo Could not create .venv. Install Python 3.9-3.12 64-bit: winget install Python.Python.3.12
    pause
    exit /b 1
  )
)

".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt -r requirements-windows.txt
if errorlevel 1 (
  echo Package install failed. If the error mentions a long path, move this folder to a shorter path such as C:\TTSKH.
  pause
  exit /b 1
)

rem GPU OCR: DirectML runs on any DirectX 12 graphics card (NVIDIA, AMD, Intel), about 3x faster.
rem Both packages provide the same module, so remove both first. Falls back to CPU OCR if needed.
".venv\Scripts\python.exe" -m pip uninstall -y onnxruntime onnxruntime-directml >nul 2>nul
".venv\Scripts\python.exe" -m pip install onnxruntime-directml
if errorlevel 1 ".venv\Scripts\python.exe" -m pip install onnxruntime

".venv\Scripts\python.exe" -X utf8 run.py doctor
pause
