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
# never touches it. If start.sh started it, this is what actually stops it;
# if it was started manually (no .dashboard.pid), this is a silent no-op —
# stop.sh only ever stops what it knows it started.
if [ -f .dashboard.pid ]; then
  pid=$(cat .dashboard.pid)
  if kill -0 "$pid" 2>/dev/null; then
    kill "$pid" 2>/dev/null || true
    echo -e "${YELLOW}Dashboard stopped.${NC}"
  fi
  rm -f .dashboard.pid
fi

echo -e "${GREEN}Done. Run ./start.sh to restart.${NC}"
