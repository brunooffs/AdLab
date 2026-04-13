#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
#  reset.sh — Full nuclear reset
#  Stops everything, wipes all volumes and checkpoints
# ─────────────────────────────────────────────────────────────────────────────

RED='\033[0;31m'; YELLOW='\033[1;33m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'; NC='\033[0m'

echo -e "${RED}=== FULL RESET — ALL DATA WILL BE LOST ===${NC}"
echo ""
echo "This will:"
echo "  - Stop all containers"
echo "  - Delete all Docker volumes (Postgres, ES, Kafka, Redis, MongoDB data)"
echo "  - Clear Spark checkpoints"
echo ""
read -p "Type 'yes' to confirm: " confirm
[[ "$confirm" != "yes" ]] && echo "Aborted." && exit 0

echo -e "\n${YELLOW}[1/4] Killing Spark applications...${NC}"
curl -s "http://localhost:8081/api/v1/applications" 2>/dev/null | \
  python3 -c "
import sys, json
try:
    apps = json.load(sys.stdin)
    for a in apps:
        attempts = a.get('attempts', [{}])
        if attempts and not attempts[0].get('completed', True):
            print(a['id'])
except: pass
" 2>/dev/null | while read app; do
  curl -s -X POST "http://localhost:8081/app/kill/?id=${app}&terminate=true" > /dev/null
  echo "  Killed: $app"
done

echo -e "${YELLOW}[2/4] Stopping all containers...${NC}"
docker compose down --timeout 20

echo -e "${YELLOW}[3/4] Removing all volumes (data wipe)...${NC}"
docker compose down -v

echo -e "${YELLOW}[4/4] Cleaning up...${NC}"
docker exec spark-master rm -rf /tmp/spark-checkpoints 2>/dev/null || true
rm -rf ./spark-jobs/__pycache__
rm -rf ./producer/__pycache__
docker system prune -f --volumes 2>/dev/null || true

echo -e "\n${GREEN}=== Reset complete ===${NC}"
echo "Run ./start.sh to restart the pipeline"
echo ""
