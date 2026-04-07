#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
#  start_pipeline.sh
#  One-shot script to spin up and run the entire clickstream pipeline.
#  Run from the project root directory.
# ─────────────────────────────────────────────────────────────────────────────
set -e

GREEN="\033[0;32m"; YELLOW="\033[0;33m"; NC="\033[0m"

step() { echo -e "${GREEN}==>${NC} $1"; }
info() { echo -e "${YELLOW}   $1${NC}"; }

step "Starting Docker services..."
docker compose up -d
info "Waiting 45s for all services to initialise..."
sleep 45

step "Setting up Elasticsearch indices..."
python3 scripts/setup_elasticsearch.py

step "Submitting Spark Structured Streaming job..."
docker exec spark-master spark-submit \
  --master spark://spark-master:7077 \
  --packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.3,org.elasticsearch:elasticsearch-spark-30_2.12:8.13.4 \
  --conf spark.sql.streaming.checkpointLocation=/tmp/spark-checkpoints \
  --conf spark.executor.memory=1g \
  --conf spark.driver.memory=1g \
  /opt/spark-apps/clickstream_streaming.py &

info "Spark job submitted (running in background)."
info "Waiting 15s before starting producer..."
sleep 15

step "Starting Kafka producer (2 events/sec)..."
python3 producer/clickstream_producer.py --rate 2

echo ""
step "Pipeline running. Access UIs:"
info "  Kafka UI:      http://localhost:8080"
info "  Spark UI:      http://localhost:8081"
info "  Kibana:        http://localhost:5601"
info "  Elasticsearch: http://localhost:9200"
