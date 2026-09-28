#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
#  produce.sh — Send a controlled batch of ad click events to Kafka.
#  Runs inside a container: no local Python or virtualenv needed.
#  Usage: ./produce.sh [events] [rate] [extra producer.py flags...]
#  Defaults: 500 events at 5/sec.  Example: ./produce.sh 2000 50 --hot-ad ad_x --buckets 4
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail
cd "$(dirname "$0")"

EVENTS=${1:-500}
RATE=${2:-5}
if [ $# -ge 2 ]; then shift 2; else set --; fi

YELLOW='\033[1;33m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'; NC='\033[0m'

echo -e "${CYAN}=== Click producer ===${NC}"
echo -e "  Events: ${EVENTS} | Rate: ${RATE}/sec | Est. time: $((EVENTS / RATE))s\n"

echo -e "${YELLOW}Starting producer container...${NC}"
docker compose --profile streaming --profile tools run --rm --build \
  producer python producer.py --events "$EVENTS" --rate "$RATE" "$@"

echo -e "\n${GREEN}Done. Check Kafka UI: http://localhost:8080${NC}"
