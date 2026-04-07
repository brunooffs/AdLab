#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# submit_job.sh
# Submits the Spark Structured Streaming job to the Spark master container.
# Run from the project root: ./scripts/submit_job.sh
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

# JARs required for Kafka + Elasticsearch connectors
# These are auto-downloaded by Spark via --packages
PACKAGES=(
  "org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.3"
  "org.elasticsearch:elasticsearch-spark-30_2.12:8.13.4"
  "org.apache.commons:commons-pool2:2.11.1"
)
PACKAGES_ARG=$(IFS=,; echo "${PACKAGES[*]}")

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Submitting Clickstream Streaming Job"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

docker exec spark-master /opt/spark/bin/spark-submit \
  --master spark://spark-master:7077 \
  --deploy-mode client \
  --packages "$PACKAGES_ARG" \
  --conf "spark.es.nodes=elasticsearch" \
  --conf "spark.es.port=9200" \
  --conf "spark.es.nodes.wan.only=true" \
  --conf "spark.sql.streaming.checkpointLocation=/tmp/spark-checkpoints" \
  --conf "spark.kafka.bootstrap.servers=kafka:9092" \
  --conf "spark.driver.extraJavaOptions=-Divy.home=/tmp/.ivy2" \
  --conf "spark.executor.extraJavaOptions=-Divy.home=/tmp/.ivy2" \
  /opt/spark-apps/streaming_job.py

echo ""
echo "✓ Job submitted."
