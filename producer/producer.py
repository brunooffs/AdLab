# ─────────────────────────────────────────────────────────────────────────────
#  producer.py — Clickstream event producer
#  Generates realistic click events using REAL advertiser and campaign
#  data loaded from PostgreSQL via SQLAlchemy.
#
#  Usage:
#    python producer.py                    # runs forever
#    python producer.py --events 1000      # sends 1000 events then stops
#    python producer.py --rate 50          # 50 events/second
#    python producer.py --hot-ad ad_xxx    # simulate hot partition scenario
# ─────────────────────────────────────────────────────────────────────────────

import argparse
import hashlib
import json
import os
import random
import signal
import time
import uuid
from datetime import datetime, timezone

from dotenv import load_dotenv
from kafka import KafkaProducer
from kafka.errors import NoBrokersAvailable

from db import load_ad_catalogue

load_dotenv()

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9094")
TOPIC           = os.getenv("KAFKA_TOPIC", "clickstream")
DEFAULT_RATE    = int(os.getenv("EVENTS_PER_SECOND", "10"))

# ── Graceful shutdown ─────────────────────────────────────────────────────────
running = True

def handle_signal(sig, frame):
    global running
    print("\nShutting down producer gracefully...")
    running = False

signal.signal(signal.SIGINT,  handle_signal)
signal.signal(signal.SIGTERM, handle_signal)


# ── Deterministic event_id ────────────────────────────────────────────────────
def generate_event_id(user_id: str, ad_id: str, session_id: str,
                       clock: float | None = None) -> str:
    """
    Deterministic SHA-256 based event ID.
    Same user + ad + session within the same minute → same ID → deduped.
    """
    ts = clock if clock is not None else time.time()
    minute_bucket = int(ts // 60) * 60
    raw = f"{user_id}|{ad_id}|{session_id}|{minute_bucket}"
    return hashlib.sha256(raw.encode()).hexdigest()


# ── Kafka producer setup ──────────────────────────────────────────────────────
def create_producer(retries: int = 10) -> KafkaProducer:
    for attempt in range(1, retries + 1):
        try:
            producer = KafkaProducer(
                bootstrap_servers=KAFKA_BOOTSTRAP,
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                key_serializer=lambda k: k.encode("utf-8") if k else None,
                # Reliability settings
                acks="all",
                retries=3,
                retry_backoff_ms=300,
                # Throughput settings
                linger_ms=10,
                batch_size=16384,
                compression_type="lz4",
            )
            print(f"Connected to Kafka at {KAFKA_BOOTSTRAP}")
            return producer
        except NoBrokersAvailable:
            print(f"Kafka not ready (attempt {attempt}/{retries}) — retrying in 3s...")
            time.sleep(3)

    raise RuntimeError(f"Could not connect to Kafka after {retries} attempts")


# ── Event generation ──────────────────────────────────────────────────────────
def generate_event(ad: dict, users: list[str], hot_ad_id: str | None = None) -> dict:
    """
    Generates one realistic clickstream event using real ad/campaign data.
    """
    user_id    = random.choice(users)
    session_id = str(uuid.uuid4())
    now        = time.time()

    # Weighted action — views are 5x more common than clicks
    action = random.choices(
        ["view", "click"],
        weights=[5, 1]
    )[0]

    # If hot_ad_id is set, force that ad to simulate a viral campaign
    target_ad = ad if hot_ad_id is None else {**ad, "ad_id": hot_ad_id}

    event = {
        # Identity
        "event_id":       generate_event_id(user_id, target_ad["ad_id"], session_id, now),
        "user_id":        user_id,
        "session_id":     session_id,

        # Ad data — from real PostgreSQL rows
        "ad_id":          target_ad["ad_id"],
        "advertiser_id":  target_ad["advertiser_id"],
        "campaign_id":    target_ad["campaign_id"],
        "ad_type":        target_ad["ad_type"],
        "market":         target_ad["market"],

        # Interaction
        "action":         action,
        "timestamp":      int(now * 1000),  # epoch milliseconds
        "ingest_time":    int(now * 1000),

        # Page context
        "rank":           random.randint(1, 5),
        "page_url":       hashlib.sha256(
                              f"https://example.com/page/{random.randint(1,100)}"
                              .encode()
                          ).hexdigest()[:16],
    }

    return event


# ── Partition key — supports hot partition simulation ─────────────────────────
def get_partition_key(event: dict, n_buckets: int = 1) -> str:
    """
    Normal ads: key = ad_id (consistent partition)
    Hot ads:    key = ad_id_<salt> (spread across N partitions)
    """
    if n_buckets <= 1:
        return event["ad_id"]
    salt = random.randint(0, n_buckets - 1)
    return f"{event['ad_id']}_{salt}"


# ── Stats printer ─────────────────────────────────────────────────────────────
def print_stats(sent: int, errors: int, start: float, last_event: dict | None):
    elapsed  = time.time() - start
    rate     = sent / elapsed if elapsed > 0 else 0
    ts       = datetime.now(timezone.utc).strftime("%H:%M:%S")
    ad_id    = last_event["ad_id"] if last_event else "—"
    action   = last_event["action"] if last_event else "—"
    print(
        f"[{ts}] sent={sent:>6} | errors={errors:>3} | "
        f"rate={rate:>6.1f}/s | last={action} on {ad_id}"
    )


# ── Main loop ─────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="AdLab clickstream producer")
    parser.add_argument("--events",  type=int,   default=0,
                        help="Total events to send (0 = infinite)")
    parser.add_argument("--rate",    type=int,   default=DEFAULT_RATE,
                        help="Events per second")
    parser.add_argument("--hot-ad",  type=str,   default=None,
                        help="Force a hot ad_id to simulate viral traffic")
    parser.add_argument("--buckets", type=int,   default=1,
                        help="Salt buckets for hot ad (anti hot-partition)")
    parser.add_argument("--users",   type=int,   default=500,
                        help="Number of simulated users")
    args = parser.parse_args()

    # ── Load real ad catalogue from PostgreSQL ────────────────────────────────
    print("Loading ad catalogue from PostgreSQL...")
    catalogue = load_ad_catalogue()

    if not catalogue:
        print("ERROR: No ads found and seeding failed. Check DB connection.")
        return

    # ── Simulate a pool of users ──────────────────────────────────────────────
    users = [f"user_{uuid.uuid4().hex[:8]}" for _ in range(args.users)]
    print(f"Simulating {args.users} users across {len(catalogue)} ads")
    print(f"Kafka topic: {TOPIC} | Rate: {args.rate} events/sec")
    if args.hot_ad:
        print(f"HOT AD MODE: forcing traffic to {args.hot_ad} "
              f"with {args.buckets} salt buckets")

    # ── Connect to Kafka ──────────────────────────────────────────────────────
    producer = create_producer()

    sent       = 0
    errors     = 0
    start_time = time.time()
    last_event = None
    interval   = 1.0 / args.rate

    print(f"\nProducing events... (Ctrl+C to stop)\n")

    while running:
        if args.events > 0 and sent >= args.events:
            print(f"\nReached target of {args.events} events.")
            break

        try:
            # Pick a random ad from the real catalogue
            ad = random.choice(catalogue)

            event = generate_event(
                ad=ad,
                users=users,
                hot_ad_id=args.hot_ad
            )

            key = get_partition_key(event, n_buckets=args.buckets)

            producer.send(
                topic=TOPIC,
                key=key,
                value=event
            )

            sent      += 1
            last_event = event

            # Print stats every 100 events
            if sent % 100 == 0:
                print_stats(sent, errors, start_time, last_event)

        except Exception as e:
            errors += 1
            print(f"Error producing event: {e}")

        time.sleep(interval)

    # ── Flush and close ───────────────────────────────────────────────────────
    print("\nFlushing remaining messages...")
    producer.flush()
    producer.close()

    print_stats(sent, errors, start_time, last_event)
    print(f"\nDone. Sent {sent} events, {errors} errors.")


if __name__ == "__main__":
    main()
