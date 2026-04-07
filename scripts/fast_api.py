# fastapi_app.py
"""
FastAPI app for querying Kafka → Spark → ScyllaDB/Elasticsearch pipeline
Exposes endpoints for:
  - Search events in Elasticsearch (full-text, filters)
  - Lookup raw events in ScyllaDB (by user_id, time range)
  - Get event statistics and aggregations
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from elasticsearch import Elasticsearch
from cassandra.cluster import Cluster

app = FastAPI(title="Event Query API", version="1.0.0")

# Database Connections
es = Elasticsearch(["https://localhost:9200"])
cluster = Cluster(["localhost"], port=9042)
session = cluster.connect()
session.set_keyspace("raw_data")


# ============================================================================
# Pydantic Models
# ============================================================================

class EventSearchQuery(BaseModel):
    query: str
    action_filter: Optional[str] = None
    time_range: Optional[dict] = None
    limit: int = 20


class RawEventQuery(BaseModel):
    user_id: str
    start_time: Optional[str] = None
    end_time: Optional[str] = None


# ============================================================================
# Health & Status
# ============================================================================

@app.get("/health")
async def health():
    """Health check"""
    try:
        es.info()
        session.execute("SELECT now() FROM system.local")
        return {"status": "healthy", "es": "ok", "scylla": "ok"}
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


# ============================================================================
# Elasticsearch Endpoints — Search & Analytics
# ============================================================================

@app.post("/search")
async def search_events(query: EventSearchQuery):
    """Full-text search in Elasticsearch"""
    try:
        es_query = {
            "bool": {
                "must": [{
                    "multi_match": {
                        "query": query.query,
                        "fields": ["action", "page", "metadata"]
                    }
                }]
            }
        }

        if query.action_filter:
            es_query["bool"]["must"].append({"term": {"action": query.action_filter}})

        if query.time_range:
            es_query["bool"]["must"].append({"range": {"timestamp": query.time_range}})

        results = es.search(index="user-events", query=es_query, size=query.limit)

        events = []
        for hit in results["hits"]["hits"]:
            source = hit["_source"]
            events.append({
                "user_id": source.get("user_id"),
                "timestamp": source.get("timestamp"),
                "action": source.get("action"),
                "page": source.get("page"),
                "metadata": source.get("metadata"),
                "_score": hit["_score"]
            })

        return {
            "total": results["hits"]["total"]["value"],
            "results": events
        }

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/trending")
async def trending_actions(time_window: str = "1h"):
    """Get trending actions using ES aggregations"""
    try:
        agg_query = {
            "query": {"range": {"timestamp": {"gte": f"now-{time_window}"}}},
            "aggs": {
                "top_actions": {
                    "terms": {"field": "action.keyword", "size": 10}
                }
            },
            "size": 0
        }

        results = es.search(index="user-events", **agg_query)
        trending = []

        for bucket in results["aggregations"]["top_actions"]["buckets"]:
            trending.append({
                "action": bucket["key"],
                "count": bucket["doc_count"]
            })

        return {
            "time_window": time_window,
            "total_events": results["hits"]["total"]["value"],
            "trending": trending
        }

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ============================================================================
# ScyllaDB Endpoints — Raw Event Lookup
# ============================================================================

@app.post("/events/user")
async def get_user_events(query: RawEventQuery):
    """Get all raw events for a user from ScyllaDB"""
    try:
        cql = "SELECT * FROM events WHERE user_id = %s"
        params = [query.user_id]

        if query.start_time or query.end_time:
            if query.start_time:
                cql += " AND timestamp >= %s"
                params.append(datetime.fromisoformat(query.start_time))
            if query.end_time:
                cql += " AND timestamp <= %s"
                params.append(datetime.fromisoformat(query.end_time))
            cql += " ALLOW FILTERING"

        cql += " ORDER BY timestamp DESC LIMIT 1000"
        rows = session.execute(cql, params)

        events = []
        for row in rows:
            events.append({
                "user_id": row.user_id,
                "timestamp": row.timestamp.isoformat() if row.timestamp else None,
                "action": row.action,
                "page": getattr(row, 'page', None),
                "metadata": getattr(row, 'metadata', None)
            })

        return {
            "user_id": query.user_id,
            "event_count": len(events),
            "events": events
        }

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/events/stats")
async def event_statistics():
    """Get stats about ScyllaDB"""
    try:
        total_rows = session.execute("SELECT COUNT(*) as count FROM events").one()
        return {
            "total_events": total_rows.count if total_rows else 0,
            "database": "scylladb",
            "status": "healthy"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Combined — Compare Both Databases
# ============================================================================

@app.get("/events/user/{user_id}/comparison")
async def user_events_comparison(user_id: str):
    """Compare ES (search) vs ScyllaDB (raw truth)"""
    try:
        # From Elasticsearch
        es_results = es.search(
            index="user-events",
            query={"term": {"user_id": user_id}},
            size=5
        )
        es_events = [hit["_source"] for hit in es_results["hits"]["hits"]]

        # From ScyllaDB
        scylla_results = session.execute(
            "SELECT * FROM events WHERE user_id = %s LIMIT 5", [user_id]
        )
        scylla_events = [
            {
                "user_id": row.user_id,
                "timestamp": row.timestamp.isoformat() if row.timestamp else None,
                "action": row.action
            }
            for row in scylla_results
        ]

        return {
            "user_id": user_id,
            "elasticsearch": {"total": es_results["hits"]["total"]["value"], "sample": es_events},
            "scylladb": {"total": len(scylla_events), "sample": scylla_events},
            "note": "ES for search, ScyllaDB is source of truth"
        }

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ============================================================================
# Replay — Recover from ES issues
# ============================================================================

@app.post("/replay")
async def replay_events(start_date: str, end_date: str, user_id_filter: Optional[str] = None):
    """Replay raw events from ScyllaDB to Elasticsearch"""
    try:
        cql = "SELECT * FROM events WHERE timestamp >= %s AND timestamp <= %s"
        params = [datetime.fromisoformat(start_date), datetime.fromisoformat(end_date)]

        if user_id_filter:
            cql += " AND user_id = %s"
            params.append(user_id_filter)

        cql += " ALLOW FILTERING LIMIT 10000"
        rows = session.execute(cql, params)
        replayed_count = 0

        for row in rows:
            doc = {
                "user_id": row.user_id,
                "timestamp": row.timestamp.isoformat() if row.timestamp else None,
                "action": row.action,
                "page": getattr(row, 'page', None),
                "metadata": getattr(row, 'metadata', None)
            }
            es.index(index="user-events", document=doc)
            replayed_count += 1

        return {
            "status": "replay_complete",
            "events_replayed": replayed_count,
            "date_range": {"start": start_date, "end": end_date}
        }

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ============================================================================
# Run
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)