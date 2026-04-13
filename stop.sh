#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
#  stop.sh — Graceful stop (keeps data intact)
#  Usage: ./stop.sh
# ─────────────────────────────────────────────────────────────────────────────

YELLOW='\033[1;33m'; GREEN='\033[0;32m'; NC='\033[0m'

echo -e "${YELLOW}Stopping all services (data preserved)...${NC}"
docker compose stop
echo -e "${GREEN}Done. Run ./start.sh to restart.${NC}"
