"""
query_es.py
-----------
Example queries against the Elasticsearch pipeline indices.
Run while the producer and streaming job are active to see live data.

Usage:
    pip install requests
    python scripts/query_es.py
"""

import json
import requests

ES = "http://localhost:9200"

def pretty(label: str, data: dict):
    print(f"\n{'━'*55}")
    print(f"  {label}")
    print(f"{'━'*55}")
    print(json.dumps(data, indent=2, default=str))


def top_pages(n: int = 5):
    """Most visited pages aggregated across all time."""
    body = {
        "size": 0,
        "aggs": {
            "top_pages": {
                "terms": {"field": "page", "size": n},
                "aggs": {
                    "total_events": {"sum": {"field": "event_count"}},
                    "avg_duration": {"avg": {"field": "avg_duration_ms"}},
                }
            }
        }
    }
    r = requests.post(f"{ES}/clicks_per_page/_search", json=body)
    buckets = r.json()["aggregations"]["top_pages"]["buckets"]
    pretty("Top Pages", [
        {"page": b["key"], "total_events": b["total_events"]["value"],
         "avg_duration_ms": round(b["avg_duration"]["value"] or 0, 1)}
        for b in buckets
    ])


def events_by_country():
    """Total events per country."""
    body = {
        "size": 0,
        "aggs": {
            "by_country": {
                "terms": {"field": "country", "size": 20},
                "aggs": {"total": {"sum": {"field": "event_count"}}}
            }
        }
    }
    r = requests.post(f"{ES}/clicks_per_country/_search", json=body)
    buckets = r.json()["aggregations"]["by_country"]["buckets"]
    pretty("Events by Country", [
        {"country": b["key"], "total_events": b["total"]["value"]}
        for b in buckets
    ])


def events_by_device():
    """Events split by device type."""
    body = {
        "size": 0,
        "aggs": {
            "by_device": {
                "terms": {"field": "device", "size": 10},
                "aggs": {"total": {"sum": {"field": "event_count"}}}
            }
        }
    }
    r = requests.post(f"{ES}/clicks_per_device/_search", json=body)
    buckets = r.json()["aggregations"]["by_device"]["buckets"]
    pretty("Events by Device", [
        {"device": b["key"], "total_events": b["total"]["value"]}
        for b in buckets
    ])


def recent_raw_events(n: int = 5):
    """Latest raw events from the clickstream_raw index."""
    body = {
        "size": n,
        "sort": [{"event_time": {"order": "desc"}}],
        "_source": ["timestamp", "user_id", "page", "action", "device", "country"],
    }
    r = requests.post(f"{ES}/clickstream_raw/_search", json=body)
    hits = r.json().get("hits", {}).get("hits", [])
    pretty(f"Last {n} Raw Events", [h["_source"] for h in hits])


def index_stats():
    """Doc counts across all pipeline indices."""
    r = requests.get(f"{ES}/_cat/indices/clicks*,clickstream*?v&format=json")
    pretty("Index Stats", r.json())


if __name__ == "__main__":
    print("Querying Elasticsearch pipeline indices…")
    for fn in [index_stats, top_pages, events_by_country, events_by_device, recent_raw_events]:
        try:
            fn()
        except Exception as e:
            print(f"  ✗ {fn.__name__} failed: {e}")
    print("\n")
