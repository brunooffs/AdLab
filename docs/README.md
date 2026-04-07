# Clickstream Big Data Pipeline

A production-grade, real-time clickstream analytics pipeline built on **Kafka → Spark → Elasticsearch → Kibana**, running entirely in Docker on Apple Silicon (M1/M2/M3).

## Architecture

```
[Python Producer]
      |
      | JSON events (2/sec)
      v
  [Apache Kafka]          ← KRaft mode, no Zookeeper
  topic: clickstream-events
      |
      | Spark reads stream
      v
[Spark Structured Streaming]
      |
      | windowed aggregations (1-min tumbling windows)
      |
      +──> clickstream-raw-events          (every event, raw)
      +──> clickstream-clicks-per-page     (page popularity)
      +──> clickstream-clicks-per-user     (user activity)
      +──> clickstream-events-by-type      (event breakdown)
      +──> clickstream-events-by-country   (geo traffic)
      +──> clickstream-events-by-device    (device split)
      +──> clickstream-avg-duration        (engagement time)
      |
      v
[Elasticsearch 8.13]
      |
      v
   [Kibana]               ← visualise & explore
```

## Project Structure

```
clickstream-pipeline/
├── docker-compose.yml          # All services
├── requirements.txt            # Python deps
├── producer/
│   └── clickstream_producer.py # Fake event generator → Kafka
├── spark-jobs/
│   └── clickstream_streaming.py# Spark Structured Streaming job
├── scripts/
│   ├── setup_elasticsearch.py  # Create ES indices + mappings
│   ├── query_es.py             # CLI queries against ES
│   └── start_pipeline.sh       # One-shot startup script
├── kibana/
│   └── index_patterns.json     # Import into Kibana
└── docs/
    └── README.md               # This file
```

## Quick Start

### 1. Prerequisites

- Docker Desktop (with ~6 GB RAM allocated)
- Python 3.10+

```bash
pip install -r requirements.txt
```

### 2. Start all Docker services

```bash
docker compose up -d
```

Wait ~45 seconds for all services to be healthy. Check with:
```bash
docker compose ps
```

### 3. Set up Elasticsearch indices

```bash
python scripts/setup_elasticsearch.py
```

### 4. Submit the Spark streaming job

```bash
docker exec spark-master spark-submit \
  --master spark://spark-master:7077 \
  --packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.3,org.elasticsearch:elasticsearch-spark-30_2.12:8.13.4 \
  --conf spark.executor.memory=1g \
  --conf spark.driver.memory=1g \
  /opt/spark-apps/clickstream_streaming.py
```

> First run will download ~200 MB of Maven packages. Subsequent runs are instant.

### 5. Start the Kafka producer

In a separate terminal:
```bash
python producer/clickstream_producer.py --rate 2
```

Options:
| Flag | Default | Description |
|------|---------|-------------|
| `--rate` | `2.0` | Events per second |
| `--topic` | `clickstream-events` | Kafka topic |
| `--bootstrap` | `localhost:9094` | Kafka broker |

### 6. Query the data

```bash
# Show all aggregations from the last 5 minutes
python scripts/query_es.py

# Specific queries
python scripts/query_es.py --query top-pages --minutes 10
python scripts/query_es.py --query active-users
python scripts/query_es.py --query event-types
python scripts/query_es.py --query countries
python scripts/query_es.py --query devices
```

## Service UIs

| Service | URL | Notes |
|---------|-----|-------|
| Kafka UI | http://localhost:8080 | Browse topics, messages, consumer groups |
| Spark Master | http://localhost:8081 | Job status, executor info |
| Spark Worker | http://localhost:8082 | Worker resource usage |
| Kibana | http://localhost:5601 | Dashboards & data exploration |
| Elasticsearch | http://localhost:9200 | Direct REST API |

## Kibana Setup

1. Open http://localhost:5601
2. Go to **Stack Management → Data Views**
3. Create a data view for each `clickstream-*` index, using:
   - `event_time` as the time field for `clickstream-raw-events`
   - `window_start` as the time field for all aggregation indices
4. Go to **Discover** or **Dashboard** to explore

## Event Schema

Each clickstream event published to Kafka:

```json
{
  "event_id":     "uuid",
  "timestamp":    "2025-03-22T14:30:00.000Z",
  "user_id":      "uuid",
  "session_id":   "uuid",
  "event_type":   "page_view | click | add_to_cart | ...",
  "page":         "/products/shoes",
  "device":       "mobile | desktop | tablet",
  "browser":      "Chrome | Firefox | Safari | Edge",
  "country":      "PT | US | GB | ...",
  "referrer":     "google.com | direct | ...",
  "ip_address":   "203.0.113.42",
  "user_agent":   "Mozilla/5.0 ...",
  "duration_ms":  4320,
  "scroll_depth": 78,
  "search_query": "running shoes",
  "product_id":   "4821",
  "cart_value":   129.99
}
```

## Stopping Everything

```bash
docker compose down          # stop containers (keeps volumes)
docker compose down -v       # stop + delete all data volumes
```

## Troubleshooting

**Spark job can't connect to Kafka**
Spark runs inside Docker and uses `kafka:9092` (internal listener). Ensure both containers are on the `pipeline` network — they are by default.

**ES connector not found**
The `--packages` flag downloads the connector at submit time. If it fails due to network issues, retry. You can also pre-download the JARs and mount them via `--jars`.

**Out of memory errors**
Increase Docker Desktop memory allocation (Settings → Resources). Recommended: 6 GB minimum, 8 GB ideal.

**Kafka UI shows no topics**
The topic is created automatically on first message. Start the producer first, then refresh Kafka UI.
