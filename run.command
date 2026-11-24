#!/usr/bin/env bash
# OBJ//TRAKR launcher for macOS (and Linux).
# First run: creates .venv and installs dependencies (a few minutes, ~1 GB).
# Usage:  bash run.command      (or double-click after: chmod +x run.command)
set -e
cd "$(dirname "$0")"
PORT="${PORT:-7860}"

# --- find a Python between 3.9 and 3.12 (PyTorch wheels exist for these) ---
PY=""
for c in python3.12 python3.11 python3.10 python3 python3.9; do
  if command -v "$c" >/dev/null 2>&1; then
    if "$c" -c 'import sys; sys.exit(0 if (3,9) <= sys.version_info[:2] <= (3,12) else 1)' 2>/dev/null; then
      PY="$(command -v "$c")"; break
    fi
  fi
done
if [ -z "$PY" ] && [ ! -x .venv/bin/python ]; then
  echo ""
  echo "  Python 3.9 - 3.12 is required."
  echo "  Install it from https://www.python.org/downloads/macos/  (3.12 recommended)"
  echo "  or with Homebrew:  brew install python@3.12"
  echo ""
  exit 1
fi

# --- one-time setup ---
if [ ! -f .venv/.installed ]; then
  echo "[setup] creating virtual environment with $PY"
  rm -rf .venv
  "$PY" -m venv .venv
  .venv/bin/python -m pip install --upgrade pip
  if [ "$(uname -s)" = "Darwin" ] && [ "$(uname -m)" = "x86_64" ]; then
    # Intel Macs: newest available torch is 2.2.x, which needs numpy < 2
    .venv/bin/python -m pip install "numpy<2"
  fi
  .venv/bin/python -m pip install -r requirements.txt
  touch .venv/.installed
  echo "[setup] done"
fi

# --- open the browser once the server answers ---
(
  for _ in $(seq 1 60); do
    if curl -s -o /dev/null "http://127.0.0.1:$PORT/"; then
      if command -v open >/dev/null; then open "http://127.0.0.1:$PORT"; else xdg-open "http://127.0.0.1:$PORT" >/dev/null 2>&1 || true; fi
      break
    fi
    sleep 1
  done
) &

PORT="$PORT" exec .venv/bin/python app.py
