#!/usr/bin/env bash
# submit_spark_job.sh
# ─────────────────────────────────────────────────────────────────────────────
# Submits the PySpark streaming job to the Spark master running in Docker.
# Run this from the project root after `docker compose up -d`.

set -euo pipefail

SPARK_MASTER="spark://spark-master:7077"
JOB_PATH="/opt/spark-apps/streaming_job.py"

# Spark + Kafka connector + Elasticsearch connector
PACKAGES=(
  "org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.3"
  "org.elasticsearch:elasticsearch-spark-30_2.12:8.13.4"
)

PACKAGES_STR=$(IFS=,; echo "${PACKAGES[*]}")

echo "──────────────────────────────────────────────────────────"
echo " Submitting Spark Structured Streaming job"
echo " Master  : $SPARK_MASTER"
echo " Job     : $JOB_PATH"
echo " Packages: $PACKAGES_STR"
echo "──────────────────────────────────────────────────────────"

docker exec spark-master spark-submit \
  --master "$SPARK_MASTER" \
  --packages "$PACKAGES_STR" \
  --conf spark.sql.shuffle.partitions=4 \
  --conf spark.es.nodes=elasticsearch \
  --conf spark.es.port=9200 \
  --conf spark.es.nodes.wan.only=true \
  --conf spark.es.index.auto.create=true \
  "$JOB_PATH"
