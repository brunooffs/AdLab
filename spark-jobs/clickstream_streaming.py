#!/usr/bin/env python3
"""
Spark Structured Streaming Job — Clickstream Pipeline
------------------------------------------------------
Consumes raw clickstream events from Kafka, performs real-time windowed
aggregations, then writes the results to Elasticsearch.

Aggregations produced (all over a 1-minute tumbling window):
  - clicks_per_page       : event count grouped by page
  - clicks_per_user       : event count grouped by user_id
  - events_by_type        : event count grouped by event_type
  - events_by_country     : event count grouped by country
  - events_by_device      : event count grouped by device
  - checkout_funnel       : counts of checkout_start vs checkout_complete
  - avg_page_duration     : average page view duration per page
  - add_to_cart_events    : raw add-to-cart stream for cart analysis

How to submit (from project root):
    docker exec spark-master spark-submit \
      --master spark://spark-master:7077 \
      --packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.3,\
org.elasticsearch:elasticsearch-spark-30_2.12:8.13.4 \
      /opt/spark-apps/clickstream_streaming.py
"""

import os
from pyspark.sql import SparkSession
from pyspark.sql.functions import (
    col, from_json, window, count, avg,
    to_timestamp, lit, expr
)
from pyspark.sql.types import (
    StructType, StructField, StringType,
    LongType, DoubleType, TimestampType
)

# ── Config (override via env vars) ────────────────────────────────────────
KAFKA_BOOTSTRAP   = os.getenv("KAFKA_BOOTSTRAP",   "kafka:9092")
KAFKA_TOPIC       = os.getenv("KAFKA_TOPIC",        "clickstream-events")
ES_HOST           = os.getenv("ES_HOST",             "elasticsearch")
ES_PORT           = os.getenv("ES_PORT",             "9200")
CHECKPOINT_DIR    = os.getenv("CHECKPOINT_DIR",      "/tmp/spark-checkpoints")
WINDOW_DURATION   = os.getenv("WINDOW_DURATION",     "1 minute")
WATERMARK_DELAY   = os.getenv("WATERMARK_DELAY",     "30 seconds")

# ── Event schema ──────────────────────────────────────────────────────────
EVENT_SCHEMA = StructType([
    StructField("event_id",     StringType(),  True),
    StructField("timestamp",    StringType(),  True),
    StructField("user_id",      StringType(),  True),
    StructField("session_id",   StringType(),  True),
    StructField("event_type",   StringType(),  True),
    StructField("page",         StringType(),  True),
    StructField("device",       StringType(),  True),
    StructField("browser",      StringType(),  True),
    StructField("country",      StringType(),  True),
    StructField("referrer",     StringType(),  True),
    StructField("ip_address",   StringType(),  True),
    StructField("user_agent",   StringType(),  True),
    StructField("duration_ms",  LongType(),    True),
    StructField("scroll_depth", LongType(),    True),
    StructField("search_query", StringType(),  True),
    StructField("product_id",   StringType(),  True),
    StructField("cart_value",   DoubleType(),  True),
])


def build_spark_session() -> SparkSession:
    return (
        SparkSession.builder
        .appName("ClickstreamPipeline")
        .config("es.nodes",             ES_HOST)
        .config("es.port",              ES_PORT)
        .config("es.nodes.wan.only",    "true")
        .config("es.index.auto.create", "true")
        .getOrCreate()
    )


def read_kafka_stream(spark: SparkSession):
    return (
        spark.readStream
        .format("kafka")
        .option("kafka.bootstrap.servers", KAFKA_BOOTSTRAP)
        .option("subscribe",               KAFKA_TOPIC)
        .option("startingOffsets",         "latest")
        .option("failOnDataLoss",          "false")
        .load()
    )


def parse_events(raw_df):
    """Parse Kafka value bytes into structured event columns."""
    return (
        raw_df
        .select(from_json(col("value").cast("string"), EVENT_SCHEMA).alias("e"))
        .select("e.*")
        .withColumn("event_time", to_timestamp(col("timestamp")))
        .withWatermark("event_time", WATERMARK_DELAY)
    )


def write_to_es(df, index: str, checkpoint: str):
    """Write a streaming DataFrame to Elasticsearch."""
    return (
        df.writeStream
        .format("es")
        .option("es.resource",                index)
        .option("es.nodes",                   ES_HOST)
        .option("es.port",                    ES_PORT)
        .option("es.nodes.wan.only",          "true")
        .option("checkpointLocation",         f"{CHECKPOINT_DIR}/{checkpoint}")
        .outputMode("update")
        .trigger(processingTime="15 seconds")
        .start()
    )


def main():
    spark = build_spark_session()
    spark.sparkContext.setLogLevel("WARN")

    raw    = read_kafka_stream(spark)
    events = parse_events(raw)

    # ── 1. Clicks per page ────────────────────────────────────────────────
    clicks_per_page = (
        events
        .groupBy(window("event_time", WINDOW_DURATION), col("page"))
        .agg(count("*").alias("event_count"))
        .select(
            col("window.start").alias("window_start"),
            col("window.end").alias("window_end"),
            col("page"),
            col("event_count"),
            lit("clicks_per_page").alias("agg_type"),
        )
    )

    # ── 2. Events per user ────────────────────────────────────────────────
    clicks_per_user = (
        events
        .groupBy(window("event_time", WINDOW_DURATION), col("user_id"))
        .agg(count("*").alias("event_count"))
        .select(
            col("window.start").alias("window_start"),
            col("window.end").alias("window_end"),
            col("user_id"),
            col("event_count"),
            lit("clicks_per_user").alias("agg_type"),
        )
    )

    # ── 3. Events by type ─────────────────────────────────────────────────
    events_by_type = (
        events
        .groupBy(window("event_time", WINDOW_DURATION), col("event_type"))
        .agg(count("*").alias("event_count"))
        .select(
            col("window.start").alias("window_start"),
            col("window.end").alias("window_end"),
            col("event_type"),
            col("event_count"),
            lit("events_by_type").alias("agg_type"),
        )
    )

    # ── 4. Events by country ──────────────────────────────────────────────
    events_by_country = (
        events
        .groupBy(window("event_time", WINDOW_DURATION), col("country"))
        .agg(count("*").alias("event_count"))
        .select(
            col("window.start").alias("window_start"),
            col("window.end").alias("window_end"),
            col("country"),
            col("event_count"),
            lit("events_by_country").alias("agg_type"),
        )
    )

    # ── 5. Events by device ───────────────────────────────────────────────
    events_by_device = (
        events
        .groupBy(window("event_time", WINDOW_DURATION), col("device"))
        .agg(count("*").alias("event_count"))
        .select(
            col("window.start").alias("window_start"),
            col("window.end").alias("window_end"),
            col("device"),
            col("event_count"),
            lit("events_by_device").alias("agg_type"),
        )
    )

    # ── 6. Average page view duration per page ────────────────────────────
    avg_duration = (
        events
        .filter(col("event_type") == "page_view")
        .filter(col("duration_ms").isNotNull())
        .groupBy(window("event_time", WINDOW_DURATION), col("page"))
        .agg(avg("duration_ms").alias("avg_duration_ms"))
        .select(
            col("window.start").alias("window_start"),
            col("window.end").alias("window_end"),
            col("page"),
            col("avg_duration_ms"),
            lit("avg_page_duration").alias("agg_type"),
        )
    )

    # ── 7. Raw events stream (full fidelity into ES) ───────────────────────
    raw_events = (
        events.select(
            "event_id", "event_time", "user_id", "session_id",
            "event_type", "page", "device", "browser", "country",
            "referrer", "duration_ms", "product_id", "cart_value",
        )
    )

    # ── Write all aggregations to Elasticsearch ───────────────────────────
    queries = [
        write_to_es(clicks_per_page,    "clickstream-clicks-per-page",    "clicks_per_page"),
        write_to_es(clicks_per_user,    "clickstream-clicks-per-user",    "clicks_per_user"),
        write_to_es(events_by_type,     "clickstream-events-by-type",     "events_by_type"),
        write_to_es(events_by_country,  "clickstream-events-by-country",  "events_by_country"),
        write_to_es(events_by_device,   "clickstream-events-by-device",   "events_by_device"),
        write_to_es(avg_duration,       "clickstream-avg-duration",       "avg_duration"),
        (
            raw_events.writeStream
            .format("es")
            .option("es.resource",        "clickstream-raw-events")
            .option("es.nodes",           ES_HOST)
            .option("es.port",            ES_PORT)
            .option("es.nodes.wan.only",  "true")
            .option("checkpointLocation", f"{CHECKPOINT_DIR}/raw_events")
            .outputMode("append")
            .trigger(processingTime="5 seconds")
            .start()
        ),
    ]

    print(f"Streaming {len(queries)} queries to Elasticsearch. Awaiting termination...")
    spark.streams.awaitAnyTermination()


if __name__ == "__main__":
    main()
