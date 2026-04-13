#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
#  start.sh — Start the full pipeline in correct order
# ─────────────────────────────────────────────────────────────────────────────

set -e
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; RED='\033[0;31m'; NC='\033[0m'

echo -e "${CYAN}=== AdLab Pipeline — Starting ===${NC}\n"

echo -e "${YELLOW}[1/5] Starting data layer...${NC}"
docker compose up -d postgres mongodb redis
sleep 15

echo -e "${YELLOW}[2/5] Starting Kafka...${NC}"
docker compose up -d kafka
echo "  Waiting for Kafka..."
sleep 20

echo -e "${YELLOW}[3/5] Starting Elasticsearch...${NC}"
docker compose up -d elasticsearch
echo "  Waiting for ES (this takes ~30s)..."
until curl -sf "http://localhost:9200/_cluster/health" | grep -qv '"status":"red"'; do
  printf "."
  sleep 5
done
echo " ready!"

echo -e "${YELLOW}[4/5] Starting remaining services...${NC}"
docker compose up -d kafka-ui kibana spark-master spark-worker cassandra prometheus grafana

echo -e "${YELLOW}[5/5] Starting API and Kong...${NC}"
docker compose up -d api
sleep 10
docker compose up -d kong

echo -e "\n${YELLOW}Running Prisma migrations...${NC}"
docker exec api npx prisma migrate deploy 2>/dev/null && \
  echo "  Migrations complete" || \
  echo "  Migrations skipped (already applied)"

echo -e "\n${YELLOW}Checking service health...${NC}"
sleep 5
docker compose ps --format "table {{.Name}}\t{{.Status}}" | grep -v "^NAME"

echo -e "\n${GREEN}=== Pipeline started! ===${NC}\n"
echo -e "${CYAN}URLs:${NC}"
echo "  API docs:      http://localhost:3000/docs"
echo "  Kong:          http://localhost:8000"
echo "  Kafka UI:      http://localhost:8080"
echo "  Kibana:        http://localhost:5601"
echo "  Spark UI:      http://localhost:8081"
echo "  Elasticsearch: http://localhost:9200"
echo "  Grafana:       http://localhost:3001  (admin/admin)"
echo "  Prometheus:    http://localhost:9090"
echo ""
echo -e "${CYAN}Next steps:${NC}"
echo "  1. Send events:  ./produce.sh 500 10"
echo "  2. Run Spark:    ./spark.sh"
echo "  3. Check status: ./status.sh"
echo ""
