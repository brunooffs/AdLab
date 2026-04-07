#!/usr/bin/env python3
"""
Clickstream Event Producer
--------------------------
Generates realistic fake user clickstream events and publishes them
to the Kafka topic `clickstream-events` at a configurable rate.

Usage:
    pip install -r requirements.txt
    python producer/clickstream_producer.py [--rate 2] [--topic clickstream-events]
"""

import argparse
import json
import random
import time
import uuid
from datetime import datetime, timezone

from faker import Faker
from kafka import KafkaProducer
from kafka.errors import NoBrokersAvailable

KAFKA_BOOTSTRAP = "localhost:9094"

PAGES = [
    "/", "/home", "/products", "/products/shoes", "/products/bags",
    "/products/jackets", "/cart", "/checkout", "/checkout/payment",
    "/checkout/confirm", "/account", "/account/orders", "/search",
    "/blog", "/about", "/contact", "/wishlist",
]

EVENTS = [
    "page_view", "page_view", "page_view",
    "click", "click",
    "add_to_cart",
    "remove_from_cart",
    "search",
    "checkout_start",
    "checkout_complete",
    "login", "logout", "scroll",
]

DEVICES   = ["desktop", "mobile", "tablet"]
BROWSERS  = ["Chrome", "Firefox", "Safari", "Edge"]
COUNTRIES = ["PT", "US", "GB", "DE", "FR", "ES", "BR", "NL", "IT", "PL"]
REFERRERS = ["google.com", "facebook.com", "instagram.com", "direct",
             "email_campaign", "twitter.com", "bing.com", ""]

fake        = Faker()
USER_POOL   = [str(uuid.uuid4()) for _ in range(200)]
SESSION_POOL = [str(uuid.uuid4()) for _ in range(500)]


def generate_event() -> dict:
    event_type = random.choice(EVENTS)
    return {
        "event_id":     str(uuid.uuid4()),
        "timestamp":    datetime.now(timezone.utc).isoformat(),
        "user_id":      random.choice(USER_POOL),
        "session_id":   random.choice(SESSION_POOL),
        "event_type":   event_type,
        "page":         random.choice(PAGES),
        "device":       random.choice(DEVICES),
        "browser":      random.choice(BROWSERS),
        "country":      random.choice(COUNTRIES),
        "referrer":     random.choice(REFERRERS),
        "ip_address":   fake.ipv4_public(),
        "user_agent":   fake.user_agent(),
        "duration_ms":  random.randint(100, 30000) if event_type == "page_view" else None,
        "scroll_depth": random.randint(10, 100)    if event_type == "scroll"    else None,
        "search_query": fake.word()                if event_type == "search"    else None,
        "product_id":   str(random.randint(1000, 9999)) if event_type in (
                            "add_to_cart", "remove_from_cart", "click") else None,
        "cart_value":   round(random.uniform(9.99, 499.99), 2) if event_type in (
                            "checkout_start", "checkout_complete", "add_to_cart") else None,
    }


def wait_for_kafka(bootstrap: str, retries: int = 10, delay: int = 3) -> KafkaProducer:
    for attempt in range(1, retries + 1):
        try:
            producer = KafkaProducer(
                bootstrap_servers=bootstrap,
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                key_serializer=lambda k: k.encode("utf-8") if k else None,
                acks="all",
                retries=3,
                max_block_ms=5000,
            )
            print(f"Connected to Kafka at {bootstrap}")
            return producer
        except NoBrokersAvailable:
            print(f"Kafka not ready (attempt {attempt}/{retries}), retrying in {delay}s...")
            time.sleep(delay)
    raise RuntimeError(f"Could not connect to Kafka at {bootstrap} after {retries} attempts.")


def main():
    parser = argparse.ArgumentParser(description="Clickstream event producer")
    parser.add_argument("--rate",      type=float, default=2.0,
                        help="Events per second (default: 2.0)")
    parser.add_argument("--topic",     default="clickstream-events",
                        help="Kafka topic (default: clickstream-events)")
    parser.add_argument("--bootstrap", default=KAFKA_BOOTSTRAP,
                        help=f"Kafka bootstrap servers (default: {KAFKA_BOOTSTRAP})")
    args = parser.parse_args()

    producer = wait_for_kafka(args.bootstrap)
    interval = 1.0 / args.rate
    count = 0

    print(f"Publishing to topic {args.topic!r} at {args.rate} events/sec. Press Ctrl+C to stop.")

    try:
        while True:
            event = generate_event()
            producer.send(topic=args.topic, key=event["user_id"], value=event)
            count += 1
            print(f"[{count:>6}] {event['timestamp']}  "
                  f"{event['event_type']:<20} user={event['user_id'][:8]}  page={event['page']}")
            time.sleep(interval)
    except KeyboardInterrupt:
        print(f"\nStopped after {count} events.")
    finally:
        producer.flush()
        producer.close()


if __name__ == "__main__":
    main()
