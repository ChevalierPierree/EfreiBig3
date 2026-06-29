#!/bin/sh
set -eu

DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
cd "$DIR"

if [ -x "$DIR/.dashboard_env/bin/streamlit" ]; then
  STREAMLIT="$DIR/.dashboard_env/bin/streamlit"
else
  python3 -m venv "$DIR/.dashboard_env"
  "$DIR/.dashboard_env/bin/pip" install -r "$DIR/requirements.txt"
  STREAMLIT="$DIR/.dashboard_env/bin/streamlit"
fi

old_pid="$(lsof -tiTCP:8501 -sTCP:LISTEN 2>/dev/null || true)"
if [ -n "$old_pid" ]; then
  kill $old_pid 2>/dev/null || true
fi

screen -S flights_dashboard -X quit >/dev/null 2>&1 || true
screen -dmS flights_dashboard sh -lc "cd '$DIR' && '$STREAMLIT' run dashboard.py --server.address 127.0.0.1 --server.port 8501 --server.headless true > streamlit_dashboard.log 2>&1"

echo "Dashboard lancé : http://127.0.0.1:8501"
echo "Pour arrêter : screen -S flights_dashboard -X quit"
