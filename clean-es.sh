#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
#  clean-es.sh — Delete all lab-created ES indices (keeps system indices)
#  Usage: ./clean-es.sh
# ─────────────────────────────────────────────────────────────────────────────

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'

echo -e "${YELLOW}Deleting lab indices from Elasticsearch...${NC}"

for index in \
  "clickstream_raw" \
  "clicks_per_page" \
  "clicks_per_device" \
  "clicks_per_country" \
  "item-click-counts" \
  "clicks-per-market" \
  "clicks-per-adtype" \
  "clicks-per-campaign"; do
  result=$(curl -sf -X DELETE "http://localhost:9200/$index" 2>/dev/null)
  if echo "$result" | grep -q '"acknowledged":true'; then
    echo -e "  ${GREEN}✓${NC} Deleted: $index"
  else
    echo "  - Skipped: $index (not found)"
  fi
done

# Clear Spark checkpoints so next run starts fresh
docker exec spark-master rm -rf /tmp/spark-checkpoints 2>/dev/null || true
echo -e "\n${GREEN}ES indices cleared. Spark checkpoints reset.${NC}"
echo "Run ./produce.sh then ./spark.sh to start fresh."
