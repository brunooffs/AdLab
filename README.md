# 🔄 Clickstream Pipeline

A production-ready streaming data pipeline built with **Kafka**, **Spark Structured Streaming**, and **Elasticsearch** — running fully locally on Apple Silicon (M1/M2/M3).

```
┌─────────────────┐     ┌─────────────────┐     ┌──────────────────┐     ┌──────────────┐
│  Python         │     │  Apache Kafka   │     │  Spark           │     │ Elasticsearch│
│  Producer       │────▶│  (KRaft)        │────▶│  Structured      │────▶│  + Kibana    │
│                 │     │  topic:         │     │  Streaming       │     │              │
│ fake click      │     │  clickstream    │     │  (aggregations)  │     │  4 indices   │
│ events @ 10/s   │     │                 │     │  10s micro-batch │     │  dashboards  │
└─────────────────┘     └─────────────────┘     └──────────────────┘     └──────────────┘
```

## Project Structure

```
clickstream-pipeline/
├── docker-compose.yml          # All services (Kafka, Spark, ES, Kibana)
├── requirements.txt            # Python dependencies for local scripts
├── config/
│   └── pipeline.env            # Environment variables reference
├── producers/
│   └── clickstream_producer.py # Kafka event generator (10 events/sec)
├── spark-jobs/
│   └── streaming_job.py        # Spark Structured Streaming job
├── scripts/
│   ├── submit_job.sh           # Submits the Spark job to the cluster
│   ├── create_kafka_topic.sh   # Creates Kafka topic with 3 partitions
│   ├── setup_es_indices.py     # Creates ES index mappings
│   └── query_es.py             # Live query helper for ES indices
└── kibana/
    └── dashboards/
        └── README.md           # Kibana dashboard setup guide
```

## Quickstart

### Prerequisites
- Docker Desktop with ~6 GB RAM allocated (Settings → Resources)
- Python 3.9+ with pip

### Step 1 — Start the stack
```bash
docker compose up -d
```

Wait ~60 seconds for all services to become healthy.

### Step 2 — Create the Kafka topic
```bash
./scripts/create_kafka_topic.sh
```

### Step 3 — Create Elasticsearch indices
```bash
pip install -r requirements.txt
python scripts/setup_es_indices.py
```

### Step 4 — Start the Spark streaming job
```bash
./scripts/submit_job.sh
```

This downloads the required Kafka + Elasticsearch JARs automatically on first run (~200MB). Subsequent runs are instant.

### Step 5 — Start the producer
In a new terminal:
```bash
python producers/clickstream_producer.py
```

You'll see output like:
```
✓ Connected to Kafka at localhost:9094
→ Publishing to topic 'clickstream' at 10 events/sec.

  [14:32:01] Sent 100 events — last: page_view on /products (US)
  [14:32:11] Sent 200 events — last: add_to_cart on /cart (DE)
```

### Step 6 — Query Elasticsearch
```bash
python scripts/query_es.py
```

### Step 7 — Visualise in Kibana
Open http://localhost:5601 and follow `kibana/dashboards/README.md`.

## Service URLs

| Service         | URL                        |
|-----------------|----------------------------|
| Kafka UI        | http://localhost:8080       |
| Spark Master UI | http://localhost:8081       |
| Spark Worker UI | http://localhost:8082       |
| Elasticsearch   | http://localhost:9200       |
| Kibana          | http://localhost:5601       |

## Elasticsearch Indices

| Index               | Description                            | Trigger         |
|---------------------|----------------------------------------|-----------------|
| `clickstream_raw`   | Every raw event (1 doc per click)      | every 10s       |
| `clicks_per_page`   | Event counts + avg duration per page   | every 30s       |
| `clicks_per_country`| Event counts per country               | every 30s       |
| `clicks_per_device` | Event counts per device + action type  | every 30s       |

## Tuning

### Increase event throughput
```bash
EVENTS_PER_SECOND=100 python producers/clickstream_producer.py
```

### Scale Spark workers
```bash
docker compose up -d --scale spark-worker=3
```

### Increase Spark worker memory (edit docker-compose.yml)
```yaml
SPARK_WORKER_MEMORY: 4g
SPARK_WORKER_CORES: 4
```

## Teardown
```bash
docker compose down          # stop containers
docker compose down -v       # stop + delete all volumes (wipes data)
```

## Architecture Notes

- **Kafka KRaft mode** — no Zookeeper needed. Single-node, 3 partitions.
- **Spark micro-batch** — 10-second trigger for raw events, 30-second for aggregations. Uses watermarking (2 min) to handle late data.
- **Elasticsearch** — security disabled for local dev. Four indices with explicit mappings for clean Kibana visualisation.
- **No Bitnami images** — all official Apache and Elastic images, fully arm64-native on M1.
