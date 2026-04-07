#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
#  scripts/setup_elasticsearch.sh
#
#  Creates Elasticsearch index mappings and Kibana data views for all
#  four clickstream indices.
#
#  Run ONCE after docker compose up -d, before starting the producer.
#  Usage:
#    bash scripts/setup_elasticsearch.sh
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

ES="http://localhost:9200"
KIBANA="http://localhost:5601"

wait_for_service() {
  local url=$1
  local name=$2
  echo "⏳  Waiting for ${name}..."
  until curl -sf "${url}" > /dev/null 2>&1; do
    sleep 3
  done
  echo "✅  ${name} is up"
}

wait_for_service "${ES}" "Elasticsearch"
wait_for_service "${KIBANA}/api/status" "Kibana"

# ── cs_raw_events ─────────────────────────────────────────────────────────
echo ""
echo "📐  Creating index mapping: cs_raw_events"
curl -sf -X PUT "${ES}/cs_raw_events" \
  -H "Content-Type: application/json" \
  -d '{
    "settings": { "number_of_shards": 1, "number_of_replicas": 0 },
    "mappings": {
      "properties": {
        "event_id":    { "type": "keyword" },
        "user_id":     { "type": "keyword" },
        "session_id":  { "type": "keyword" },
        "event_type":  { "type": "keyword" },
        "page":        { "type": "keyword" },
        "referrer":    { "type": "keyword" },
        "device":      { "type": "keyword" },
        "country":     { "type": "keyword" },
        "duration_ms": { "type": "integer" },
        "event_time":  { "type": "date" }
      }
    }
  }' && echo " ✓ cs_raw_events"

# ── cs_page_popularity ────────────────────────────────────────────────────
echo "📐  Creating index mapping: cs_page_popularity"
curl -sf -X PUT "${ES}/cs_page_popularity" \
  -H "Content-Type: application/json" \
  -d '{
    "settings": { "number_of_shards": 1, "number_of_replicas": 0 },
    "mappings": {
      "properties": {
        "window_start":    { "type": "date" },
        "window_end":      { "type": "date" },
        "page":            { "type": "keyword" },
        "event_type":      { "type": "keyword" },
        "event_count":     { "type": "long" },
        "unique_users":    { "type": "long" },
        "avg_duration_ms": { "type": "double" }
      }
    }
  }' && echo " ✓ cs_page_popularity"

# ── cs_user_activity ──────────────────────────────────────────────────────
echo "📐  Creating index mapping: cs_user_activity"
curl -sf -X PUT "${ES}/cs_user_activity" \
  -H "Content-Type: application/json" \
  -d '{
    "settings": { "number_of_shards": 1, "number_of_replicas": 0 },
    "mappings": {
      "properties": {
        "window_start":      { "type": "date" },
        "window_end":        { "type": "date" },
        "user_id":           { "type": "keyword" },
        "device":            { "type": "keyword" },
        "country":           { "type": "keyword" },
        "total_events":      { "type": "long" },
        "pages_visited":     { "type": "integer" },
        "event_types":       { "type": "keyword" },
        "total_duration_ms": { "type": "long" }
      }
    }
  }' && echo " ✓ cs_user_activity"

# ── cs_geo_device ─────────────────────────────────────────────────────────
echo "📐  Creating index mapping: cs_geo_device"
curl -sf -X PUT "${ES}/cs_geo_device" \
  -H "Content-Type: application/json" \
  -d '{
    "settings": { "number_of_shards": 1, "number_of_replicas": 0 },
    "mappings": {
      "properties": {
        "window_start":     { "type": "date" },
        "window_end":       { "type": "date" },
        "country":          { "type": "keyword" },
        "device":           { "type": "keyword" },
        "event_count":      { "type": "long" },
        "unique_users":     { "type": "long" },
        "unique_sessions":  { "type": "long" }
      }
    }
  }' && echo " ✓ cs_geo_device"

# ── Kibana Data Views ─────────────────────────────────────────────────────
echo ""
echo "📊  Creating Kibana data views..."

create_data_view() {
  local id=$1
  local title=$2
  local time_field=$3
  curl -sf -X POST "${KIBANA}/api/data_views/data_view" \
    -H "Content-Type: application/json" \
    -H "kbn-xsrf: true" \
    -d "{
      \"data_view\": {
        \"id\": \"${id}\",
        \"title\": \"${title}\",
        \"timeFieldName\": \"${time_field}\"
      }
    }" > /dev/null && echo " ✓ Data view: ${title}"
}

create_data_view "cs_raw_events"      "cs_raw_events"      "event_time"
create_data_view "cs_page_popularity" "cs_page_popularity" "window_start"
create_data_view "cs_user_activity"   "cs_user_activity"   "window_start"
create_data_view "cs_geo_device"      "cs_geo_device"      "window_start"

echo ""
echo "🎉  Setup complete!"
echo ""
echo "   Next steps:"
echo "   1. Start the producer:  python producers/clickstream_producer.py"
echo "   2. Submit Spark job:    bash scripts/submit_job.sh"
echo "   3. Open Kibana:         http://localhost:5601"
echo "   4. Open Kafka UI:       http://localhost:8080"
echo "   5. Open Spark UI:       http://localhost:8081"
echo ""
