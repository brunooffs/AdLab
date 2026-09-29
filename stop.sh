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
echo -e "${GREEN}Done. Run ./start.sh to restart.${NC}"
