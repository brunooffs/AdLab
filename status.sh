#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
#  status.sh — Check health of all services + data counts
# ─────────────────────────────────────────────────────────────────────────────

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
cd "$(dirname "$0")"

echo -e "${CYAN}=== AdLab Pipeline Status ===${NC}\n"

check_http() {
  local name=$1 url=$2 container=${3:-}
  if [ -n "$container" ] && ! docker ps --format "{{.Names}}" | grep -q "^${container}$"; then
    echo -e "  ${YELLOW}○${NC} $name (not started)"
    return
  fi
  if curl -sf "$url" > /dev/null 2>&1; then
    echo -e "  ${GREEN}✓${NC} $name"
  else
    echo -e "  ${RED}✗${NC} $name — unreachable"
  fi
}

check_container() {
  local name=$1 optional=${2:-}
  if docker ps --format "{{.Names}}" | grep -q "^${name}$"; then
    echo -e "  ${GREEN}✓${NC} $name (running)"
  elif [ "$optional" = "opt" ]; then
    echo -e "  ${YELLOW}○${NC} $name (not started)"
  else
    echo -e "  ${RED}✗${NC} $name (not running)"
  fi
}

echo -e "${YELLOW}HTTP Services:${NC}"
check_http "Kafka UI        :8080" "http://localhost:8080" kafka-ui
check_http "Elasticsearch   :9200" "http://localhost:9200" elasticsearch
check_http "Kibana          :5601" "http://localhost:5601/api/status" kibana
check_http "Spark master    :8081" "http://localhost:8081" spark-master
check_http "Node API        :3000" "http://localhost:3000/health" api
check_http "Kong            :8000" "http://localhost:8000/health" kong
check_http "Prometheus      :9090" "http://localhost:9090/-/healthy" prometheus
check_http "Grafana         :3001" "http://localhost:3001/api/health" grafana
check_http "Tempo           :3200" "http://localhost:3200/ready" tempo

echo -e "\n${YELLOW}Container Services:${NC}"
check_container "kafka" opt
check_container "postgres"
check_container "mongodb"
check_container "redis"
check_container "cassandra" opt
check_container "spark-worker" opt
check_container "keycloak" opt

echo -e "\n${YELLOW}Container memory usage:${NC}"
docker stats --no-stream --format "  {{.Name}}\t{{.MemUsage}}\t{{.CPUPerc}}" \
  2>/dev/null | sort -k2 -h -r | head -15

echo -e "\n${YELLOW}Elasticsearch indices:${NC}"
curl -sf "http://localhost:9200/_cat/indices?v&h=index,docs.count,store.size" \
  2>/dev/null | grep -v "^\." | column -t || echo "  ES unreachable"

echo -e "\n${YELLOW}Kafka topics:${NC}"
docker exec kafka /opt/kafka/bin/kafka-topics.sh \
  --bootstrap-server localhost:9092 --list 2>/dev/null \
  | grep -v "^$" | sed 's/^/  /' || echo "  No topics found"

echo -e "\n${YELLOW}Kafka message count (clickstream):${NC}"
docker exec kafka /opt/kafka/bin/kafka-run-class.sh \
  kafka.tools.GetOffsetShell \
  --broker-list localhost:9092 \
  --topic clickstream \
  --time -1 2>/dev/null \
  | awk -F: '{sum += $3} END {print "  Total messages: " sum}' \
  || echo "  clickstream topic not found"

echo -e "\n${YELLOW}PostgreSQL tables:${NC}"
docker exec postgres psql -U lab -d adlab -t -c \
  'SELECT COUNT(*) || '"'"' advertisers'"'"' FROM "Advertiser"; SELECT COUNT(*) || '"'"' campaigns'"'"' FROM "Campaign";' \
  2>/dev/null | grep -v "^$" | sed 's/^/  /' || echo "  Postgres unreachable"

echo ""
