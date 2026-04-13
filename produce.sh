#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
#  produce.sh — Send a small controlled batch of clickstream events
#  Usage: ./produce.sh [events] [rate]
#  Defaults: 500 events at 5/sec — light enough for a local lab
# ─────────────────────────────────────────────────────────────────────────────

EVENTS=${1:-500}
RATE=${2:-5}
YELLOW='\033[1;33m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'; NC='\033[0m'

echo -e "${CYAN}=== Clickstream Producer ===${NC}"
echo -e "  Events: ${EVENTS} | Rate: ${RATE}/sec"
echo -e "  Estimated time: $((EVENTS / RATE))s\n"

# Check producer directory
if [ ! -f "./producer/producer.py" ]; then
  echo "ERROR: producer/producer.py not found. Run from Python-Lab root."
  exit 1
fi

# Check virtual env
if [ -z "$VIRTUAL_ENV" ]; then
  echo -e "${YELLOW}Activating venv...${NC}"
  source .venv/bin/activate 2>/dev/null || source venv/bin/activate 2>/dev/null || {
    echo "No venv found — running with system Python"
  }
fi

echo -e "${YELLOW}Starting producer...${NC}"
cd producer && python producer.py --events "$EVENTS" --rate "$RATE"
echo -e "\n${GREEN}Done! Check Kafka UI: http://localhost:8080${NC}"
