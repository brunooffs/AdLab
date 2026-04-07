"""
clickstream_producer.py
-----------------------
Generates synthetic user clickstream events and publishes them to Kafka.

Each event represents a user action on a fictional e-commerce website and
contains: user_id, session_id, timestamp, page, action, device, country,
referrer, and duration_ms.

Usage:
    pip install kafka-python faker
    python producers/clickstream_producer.py

Environment variables (optional):
    KAFKA_BOOTSTRAP_SERVERS  default: localhost:9094
    KAFKA_TOPIC              default: clickstream
    EVENTS_PER_SECOND        default: 10
"""

import json
import os
import random
import time
import uuid
from datetime import datetime, timezone

from faker import Faker
from kafka import KafkaProducer
from kafka.errors import NoBrokersAvailable

fake = Faker()

# ── Config ────────────────────────────────────────────────────────────────────
BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9094")
TOPIC             = os.getenv("KAFKA_TOPIC", "clickstream")
EVENTS_PER_SECOND = int(os.getenv("EVENTS_PER_SECOND", "10"))
SLEEP_INTERVAL    = 1.0 / EVENTS_PER_SECOND

# ── Realistic-looking site pages ──────────────────────────────────────────────
PAGES = [
    "/", "/products", "/products/shoes", "/products/bags",
    "/products/electronics", "/cart", "/checkout",
    "/account", "/account/orders", "/search",
    "/blog", "/about", "/contact",
]

ACTIONS = [
    "page_view", "page_view", "page_view",   # page_view is most common
    "click", "click",
    "add_to_cart", "remove_from_cart",
    "search", "purchase",
    "sign_in", "sign_out",
    "scroll", "scroll",
]

DEVICES   = ["desktop", "mobile", "tablet"]
COUNTRIES = ["US", "GB", "DE", "FR", "BR", "PT", "ES", "NL", "CA", "AU"]
REFERRERS = ["google", "direct", "facebook", "instagram", "email", "twitter", "bing"]

# ── Simulate a small pool of recurring users & sessions ───────────────────────
USER_POOL    = [str(uuid.uuid4()) for _ in range(200)]
SESSION_POOL = [str(uuid.uuid4()) for _ in range(50)]


def make_event() -> dict:
    return {
        "event_id":    str(uuid.uuid4()),
        "timestamp":   datetime.now(timezone.utc).isoformat(),
        "user_id":     random.choice(USER_POOL),
        "session_id":  random.choice(SESSION_POOL),
        "page":        random.choice(PAGES),
        "action":      random.choice(ACTIONS),
        "device":      random.choice(DEVICES),
        "country":     random.choice(COUNTRIES),
        "referrer":    random.choice(REFERRERS),
        "duration_ms": random.randint(200, 15000),
        "scroll_depth": random.randint(0, 100),
    }


def connect(retries: int = 10, delay: int = 5) -> KafkaProducer:
    for attempt in range(1, retries + 1):
        try:
            producer = KafkaProducer(
                bootstrap_servers=BOOTSTRAP_SERVERS,
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                acks="all",
                retries=3,
            )
            print(f"✓ Connected to Kafka at {BOOTSTRAP_SERVERS}")
            return producer
        except NoBrokersAvailable:
            print(f"  Kafka not ready (attempt {attempt}/{retries}), retrying in {delay}s…")
            time.sleep(delay)
    raise RuntimeError("Could not connect to Kafka after multiple attempts.")


def main():
    producer = connect()
    print(f"→ Publishing to topic '{TOPIC}' at {EVENTS_PER_SECOND} events/sec. Press Ctrl+C to stop.\n")

    sent = 0
    try:
        while True:
            event = make_event()
            producer.send(TOPIC, value=event)
            sent += 1

            if sent % 100 == 0:
                producer.flush()
                print(f"  [{datetime.now().strftime('%H:%M:%S')}] Sent {sent} events — last: {event['action']} on {event['page']} ({event['country']})")

            time.sleep(SLEEP_INTERVAL)

    except KeyboardInterrupt:
        print(f"\n✓ Stopped. Total events sent: {sent}")
    finally:
        producer.flush()
        producer.close()


if __name__ == "__main__":
    main()
