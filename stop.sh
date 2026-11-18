#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
#  stop.sh — Graceful stop of every profile (keeps data intact)
#  Usage: ./stop.sh
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail
cd "$(dirname "$0")"

YELLOW='\033[1;33m'; GREEN='\033[0;32m'; NC='\033[0m'

echo -e "${YELLOW}Stopping all services (data preserved)...${NC}"
docker compose --profile gateway --profile streaming --profile analytics \
  --profile observability --profile extras --profile tools stop

# Dashboard is a host-run process, not a container — docker compose stop above
# never touches it. .dashboard.pid covers the case start.sh started it fresh;
# it's gone if the dashboard was started by hand (e.g. `node dashboard/
# server.js &` directly), or if start.sh found port 4400 already open and so
# never wrote a new pid at all. Falling back to whatever's actually listening
# on :4400 catches both of those too, so stop.sh means stop either way.
DASHBOARD_STOPPED=0
if [ -f .dashboard.pid ]; then
  pid=$(cat .dashboard.pid)
  if kill -0 "$pid" 2>/dev/null; then
    kill "$pid" 2>/dev/null || true
    DASHBOARD_STOPPED=1
  fi
  rm -f .dashboard.pid
fi
if command -v lsof >/dev/null 2>&1; then
  port_pids=$(lsof -ti:4400 2>/dev/null || true)
  if [ -n "$port_pids" ]; then
    kill $port_pids 2>/dev/null || true
    DASHBOARD_STOPPED=1
  fi
fi
[ "$DASHBOARD_STOPPED" -eq 1 ] && echo -e "${YELLOW}Dashboard stopped.${NC}"

echo -e "${GREEN}Done. Run ./start.sh to restart.${NC}"
