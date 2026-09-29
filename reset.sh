#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
#  reset.sh — Full reset of THIS project: removes its containers and volumes.
#  Only touches the 'adlab' compose project — other Docker data is left alone.
#  Usage: ./reset.sh [--yes]
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail
cd "$(dirname "$0")"

RED='\033[0;31m'; YELLOW='\033[1;33m'; GREEN='\033[0;32m'; NC='\033[0m'

echo -e "${RED}=== RESET — all AdLab data will be lost ===${NC}"
echo "  - removes every AdLab container"
echo "  - deletes the AdLab volumes (Postgres, Elasticsearch, Kafka, Redis, MongoDB, ...)"
echo "  - Spark checkpoints go with the containers"
echo ""
if [ "${1:-}" != "--yes" ]; then
  read -r -p "Type 'yes' to confirm: " confirm
  [ "$confirm" = "yes" ] || { echo "Aborted."; exit 0; }
fi

echo -e "\n${YELLOW}Removing containers and volumes...${NC}"
docker compose --profile gateway --profile streaming --profile analytics \
  --profile observability --profile extras --profile tools \
  down -v --remove-orphans --timeout 20

rm -rf ./spark-jobs/__pycache__ ./producer/__pycache__

echo -e "\n${GREEN}=== Reset complete ===${NC}"
echo "Run ./start.sh to start again."
