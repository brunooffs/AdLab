# AdLab Management Scripts

## Quick reference

| Script | What it does |
|---|---|
| `./start.sh` | Start all services in correct order |
| `./stop.sh` | Graceful stop — data preserved |
| `./reset.sh` | Nuclear reset — wipes ALL data |
| `./status.sh` | Health check + memory usage |
| `./produce.sh [events] [rate]` | Send clickstream events to Kafka |
| `./spark.sh` | Submit Spark streaming job |
| `./clean-es.sh` | Delete lab indices from ES only |

## Typical workflow

```bash
# First time or after reset
./start.sh               # start everything
./produce.sh 500 5       # 500 events at 5/sec
./spark.sh               # process events → ES
./status.sh              # verify everything is working
```

## Low memory workflow (recommended for local)

```bash
./produce.sh 200 3       # small batch — 200 events at 3/sec
# In a second terminal:
./spark.sh               # runs Spark, Ctrl+C when done
```

## If services crash

```bash
./status.sh              # identify what's down
docker compose restart elasticsearch
docker compose restart kibana
```

## Full reset and restart

```bash
./reset.sh               # wipes everything
./start.sh               # fresh start
./produce.sh 300 5       # small sample
./spark.sh
```

## Keycloak (starts manually — saves memory)

```bash
docker compose up -d keycloak
```

## Memory budget (approximate)

| Service | Memory |
|---|---|
| Elasticsearch | ~300MB |
| Kafka | ~300MB |
| Spark master + worker | ~600MB |
| Node.js API | ~150MB |
| MongoDB | ~150MB |
| PostgreSQL | ~50MB |
| Redis | ~30MB |
| Kong + Prometheus + Grafana + Kibana | ~600MB |
| **Total** | **~2.2GB** |
