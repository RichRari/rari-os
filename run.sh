#!/usr/bin/env bash
# Starts Rari OS. First run sets up a Python virtual environment automatically.
set -e
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
  echo "First run: setting up Python environment..."
  python3 -m venv .venv
  .venv/bin/pip install -q --upgrade pip
  .venv/bin/pip install -q -r requirements.txt
fi
[ -f .env ] || cp .env.example .env

PORT=$(grep -E '^RARI_OS_PORT=' .env | cut -d= -f2)
PORT=${PORT:-8787}
echo "Rari OS running at http://127.0.0.1:$PORT  (Ctrl+C to stop)"
# Bound to 127.0.0.1 so only this Mac can reach the control panel.
exec .venv/bin/uvicorn rari_os.main:app --host 127.0.0.1 --port "$PORT"
