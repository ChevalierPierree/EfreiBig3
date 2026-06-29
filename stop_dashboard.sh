#!/bin/sh
screen -S flights_dashboard -X quit >/dev/null 2>&1 || true
old_pid="$(lsof -tiTCP:8501 -sTCP:LISTEN 2>/dev/null || true)"
if [ -n "$old_pid" ]; then
  kill $old_pid 2>/dev/null || true
fi
echo "Dashboard arrêté."
