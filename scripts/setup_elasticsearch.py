#!/usr/bin/env python3
"""
Elasticsearch Index Setup
--------------------------
Creates all required indices with proper mappings before the pipeline starts.
Run this once after Elasticsearch is healthy.

Usage:
    python scripts/setup_elasticsearch.py
"""

import time
from elasticsearch import Elasticsearch, ConnectionError

ES_HOST = "http://localhost:9200"

INDICES = {
    "clickstream-raw-events": {
        "mappings": {
            "properties": {
                "event_id":    {"type": "keyword"},
                "event_time":  {"type": "date"},
                "user_id":     {"type": "keyword"},
                "session_id":  {"type": "keyword"},
                "event_type":  {"type": "keyword"},
                "page":        {"type": "keyword"},
                "device":      {"type": "keyword"},
                "browser":     {"type": "keyword"},
                "country":     {"type": "keyword"},
                "referrer":    {"type": "keyword"},
                "duration_ms": {"type": "long"},
                "product_id":  {"type": "keyword"},
                "cart_value":  {"type": "float"},
            }
        }
    },
    "clickstream-clicks-per-page": {
        "mappings": {
            "properties": {
                "window_start": {"type": "date"},
                "window_end":   {"type": "date"},
                "page":         {"type": "keyword"},
                "event_count":  {"type": "long"},
                "agg_type":     {"type": "keyword"},
            }
        }
    },
    "clickstream-clicks-per-user": {
        "mappings": {
            "properties": {
                "window_start": {"type": "date"},
                "window_end":   {"type": "date"},
                "user_id":      {"type": "keyword"},
                "event_count":  {"type": "long"},
                "agg_type":     {"type": "keyword"},
            }
        }
    },
    "clickstream-events-by-type": {
        "mappings": {
            "properties": {
                "window_start": {"type": "date"},
                "window_end":   {"type": "date"},
                "event_type":   {"type": "keyword"},
                "event_count":  {"type": "long"},
                "agg_type":     {"type": "keyword"},
            }
        }
    },
    "clickstream-events-by-country": {
        "mappings": {
            "properties": {
                "window_start": {"type": "date"},
                "window_end":   {"type": "date"},
                "country":      {"type": "keyword"},
                "event_count":  {"type": "long"},
                "agg_type":     {"type": "keyword"},
            }
        }
    },
    "clickstream-events-by-device": {
        "mappings": {
            "properties": {
                "window_start": {"type": "date"},
                "window_end":   {"type": "date"},
                "device":       {"type": "keyword"},
                "event_count":  {"type": "long"},
                "agg_type":     {"type": "keyword"},
            }
        }
    },
    "clickstream-avg-duration": {
        "mappings": {
            "properties": {
                "window_start":   {"type": "date"},
                "window_end":     {"type": "date"},
                "page":           {"type": "keyword"},
                "avg_duration_ms":{"type": "float"},
                "agg_type":       {"type": "keyword"},
            }
        }
    },
}


def wait_for_es(es: Elasticsearch, retries: int = 20, delay: int = 5):
    for attempt in range(1, retries + 1):
        try:
            if es.ping():
                print(f"Connected to Elasticsearch at {ES_HOST}")
                return
        except ConnectionError:
            pass
        print(f"ES not ready (attempt {attempt}/{retries}), retrying in {delay}s...")
        time.sleep(delay)
    raise RuntimeError("Could not connect to Elasticsearch.")


def main():
    es = Elasticsearch(ES_HOST)
    wait_for_es(es)

    for name, body in INDICES.items():
        if es.indices.exists(index=name):
            print(f"  [skip]    {name}  (already exists)")
        else:
            es.indices.create(index=name, body=body)
            print(f"  [created] {name}")

    print("\nAll indices ready.")


if __name__ == "__main__":
    main()
