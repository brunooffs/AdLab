#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
#  spark.sh — Submit the Spark streaming job cleanly
#  Kills any existing Spark apps before submitting
#  Optional env: SPARK_APP (default adclick_streaming.py; adclick_runner.py adds RUN_SECONDS /
#  STOP_FILE stop conditions), KAFKA_TOPIC (default clickstream)
# ─────────────────────────────────────────────────────────────────────────────

YELLOW='\033[1;33m'; GREEN='\033[0;32m'; RED='\033[0;31m'; CYAN='\033[0;36m'; NC='\033[0m'
cd "$(dirname "$0")"

echo -e "${CYAN}=== Spark Streaming Job ===${NC}\n"

# Check spark-master is running
if ! docker ps --format "{{.Names}}" | grep -q "^spark-master$"; then
  echo -e "${RED}spark-master is not running. Run ./start.sh first.${NC}"
  exit 1
fi

# Check the script exists and has content on Mac
if [ ! -s "./spark-jobs/adclick_streaming.py" ]; then
  echo -e "${RED}spark-jobs/adclick_streaming.py is missing or empty.${NC}"
  exit 1
fi

# Kill any existing running Spark applications
echo -e "${YELLOW}Killing any existing Spark applications...${NC}"
RUNNING_APPS=$(curl -s "http://localhost:8081/api/v1/applications" 2>/dev/null | \
  python3 -c "
import sys, json
try:
    apps = json.load(sys.stdin)
    for a in apps:
        attempts = a.get('attempts', [{}])
        if attempts and not attempts[0].get('completed', True):
            print(a['id'])
except:
    pass
" 2>/dev/null)

if [ -n "$RUNNING_APPS" ]; then
  for app in $RUNNING_APPS; do
    curl -s -X POST "http://localhost:8081/app/kill/?id=${app}&terminate=true" > /dev/null
    echo "  Killed: $app"
  done
  sleep 5
else
  echo "  No running apps found"
fi

# Wipe checkpoints
echo -e "${YELLOW}Clearing Spark checkpoints...${NC}"
docker exec spark-master rm -rf /tmp/spark-checkpoints
docker exec spark-master mkdir -p /home/spark/.ivy2/cache 2>/dev/null || true

echo -e "${YELLOW}Submitting Spark job...${NC}"
echo -e "  Kafka:  kafka:9092/clickstream"
echo -e "  ES:     http://elasticsearch:9200"
echo -e "  JARs:   baked into the Spark image (spark/Dockerfile)\n"

docker exec -e PYTHONUNBUFFERED=1 -e RUN_SECONDS -e STOP_FILE -e KAFKA_TOPIC \
  spark-master /opt/spark/bin/spark-submit \
  --master spark://spark-master:7077 \
  --conf "spark.executor.memory=1g" \
  --conf "spark.driver.memory=512m" \
  "/opt/spark-apps/${SPARK_APP:-adclick_streaming.py}"

echo -e "\n${GREEN}Spark job finished.${NC}"
