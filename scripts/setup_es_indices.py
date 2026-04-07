"""
setup_es_indices.py
-------------------
Creates Elasticsearch index mappings for all pipeline indices before
the Spark job starts writing. Run this once after `docker compose up`.

Usage:
    pip install requests
    python scripts/setup_es_indices.py
"""

import json
import sys
import time
import requests

ES_URL = "http://localhost:9200"

INDICES = {
    "clickstream_raw": {
        "mappings": {
            "properties": {
                "event_id":    {"type": "keyword"},
                "timestamp":   {"type": "date"},
                "user_id":     {"type": "keyword"},
                "session_id":  {"type": "keyword"},
                "page":        {"type": "keyword"},
                "action":      {"type": "keyword"},
                "device":      {"type": "keyword"},
                "country":     {"type": "keyword"},
                "referrer":    {"type": "keyword"},
                "duration_ms": {"type": "integer"},
                "scroll_depth":{"type": "integer"},
                "event_time":  {"type": "date"},
            }
        }
    },
    "clicks_per_page": {
        "mappings": {
            "properties": {
                "window_start":     {"type": "date"},
                "window_end":       {"type": "date"},
                "page":             {"type": "keyword"},
                "event_count":      {"type": "long"},
                "avg_duration_ms":  {"type": "float"},
                "avg_scroll_depth": {"type": "float"},
            }
        }
    },
    "clicks_per_country": {
        "mappings": {
            "properties": {
                "window_start":    {"type": "date"},
                "window_end":      {"type": "date"},
                "country":         {"type": "keyword"},
                "event_count":     {"type": "long"},
                "avg_duration_ms": {"type": "float"},
            }
        }
    },
    "clicks_per_device": {
        "mappings": {
            "properties": {
                "window_start": {"type": "date"},
                "window_end":   {"type": "date"},
                "device":       {"type": "keyword"},
                "action":       {"type": "keyword"},
                "event_count":  {"type": "long"},
            }
        }
    },
}


def wait_for_es(retries: int = 12, delay: int = 5):
    print(f"Waiting for Elasticsearch at {ES_URL}…")
    for i in range(retries):
        try:
            r = requests.get(f"{ES_URL}/_cluster/health", timeout=5)
            if r.status_code == 200 and r.json().get("status") != "red":
                print(f"✓ Elasticsearch is up ({r.json()['status']})\n")
                return
        except requests.exceptions.ConnectionError:
            pass
        print(f"  Not ready yet (attempt {i+1}/{retries}), retrying in {delay}s…")
        time.sleep(delay)
    print("✗ Could not connect to Elasticsearch. Is Docker running?")
    sys.exit(1)


def create_index(name: str, body: dict):
    url = f"{ES_URL}/{name}"
    # Check if already exists
    r = requests.head(url)
    if r.status_code == 200:
        print(f"  ↷ Index '{name}' already exists, skipping.")
        return
    r = requests.put(url, headers={"Content-Type": "application/json"}, data=json.dumps(body))
    if r.status_code in (200, 201):
        print(f"  ✓ Created index '{name}'")
    else:
        print(f"  ✗ Failed to create '{name}': {r.text}")


def main():
    wait_for_es()
    print("Creating indices…")
    for name, body in INDICES.items():
        create_index(name, body)
    print("\n✓ All indices ready.")
    print(f"\nKibana: http://localhost:5601")
    print(f"Elasticsearch: {ES_URL}")


if __name__ == "__main__":
    main()
