@echo off
rem OBJ//TRAKR launcher for Windows. First run creates .venv and installs dependencies.
cd /d "%~dp0"
if not exist .venv\.installed (
  echo [setup] creating virtual environment...
  if exist .venv rmdir /s /q .venv
  py -3 -m venv .venv || python -m venv .venv || (echo Python 3.9-3.12 is required: https://www.python.org/downloads/ & pause & exit /b 1)
  .venv\Scripts\python.exe -m pip install --upgrade pip
  rem NVIDIA GPU users: replace "cpu" below with e.g. "cu124" for CUDA acceleration
  .venv\Scripts\python.exe -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu || (pause & exit /b 1)
  .venv\Scripts\python.exe -m pip install -r requirements.txt || (pause & exit /b 1)
  type nul > .venv\.installed
)
start "" http://127.0.0.1:7860
.venv\Scripts\python.exe app.py
pause
