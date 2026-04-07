#!/usr/bin/env bash
# Creates the clickstream Kafka topic explicitly with desired partitions.
# Run after docker compose up if you want manual control over partition count.
set -euo pipefail

docker exec kafka /opt/kafka/bin/kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --create \
  --if-not-exists \
  --topic clickstream \
  --partitions 3 \
  --replication-factor 1

echo "✓ Topic 'clickstream' ready."
