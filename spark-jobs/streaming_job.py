"""
streaming_job.py
----------------
Spark Structured Streaming job that:
  1. Consumes raw clickstream events from Kafka topic `clickstream`
  2. Parses and enriches each event
  3. Computes rolling aggregations over a 1-minute tumbling window:
       - clicks_per_page     → index: clicks_per_page
       - clicks_per_country  → index: clicks_per_country
       - clicks_per_device   → index: clicks_per_device
       - raw_events          → index: clickstream_raw  (every event)
  4. Writes results to Elasticsearch via the elasticsearch-hadoop connector

Run via scripts/submit_job.sh (which sets up all required JARs).

Environment variables:
    KAFKA_BOOTSTRAP_SERVERS   default: kafka:9092
    KAFKA_TOPIC               default: clickstream
    ES_NODES                  default: elasticsearch
    ES_PORT                   default: 9200
    CHECKPOINT_DIR            default: /tmp/spark-checkpoints
"""

import os
from pyspark.sql import SparkSession
from pyspark.sql.functions import (
    col, from_json, window, count, avg,
    to_timestamp, lit, current_timestamp,
    sum as spark_sum,
)
from pyspark.sql.types import (
    StructType, StructField,
    StringType, IntegerType, TimestampType,
)

# ── Config ────────────────────────────────────────────────────────────────────
KAFKA_SERVERS  = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
KAFKA_TOPIC    = os.getenv("KAFKA_TOPIC", "clickstream")
ES_NODES       = os.getenv("ES_NODES", "elasticsearch")
ES_PORT        = os.getenv("ES_PORT", "9200")
CHECKPOINT_DIR = os.getenv("CHECKPOINT_DIR", "/tmp/spark-checkpoints")

# ── Event schema (mirrors producer output) ────────────────────────────────────
EVENT_SCHEMA = StructType([
    StructField("event_id",    StringType(),    True),
    StructField("timestamp",   StringType(),    True),
    StructField("user_id",     StringType(),    True),
    StructField("session_id",  StringType(),    True),
    StructField("page",        StringType(),    True),
    StructField("action",      StringType(),    True),
    StructField("device",      StringType(),    True),
    StructField("country",     StringType(),    True),
    StructField("referrer",    StringType(),    True),
    StructField("duration_ms", IntegerType(),   True),
    StructField("scroll_depth",IntegerType(),   True),
])

# ── ES writer helper ──────────────────────────────────────────────────────────
def es_options(index: str) -> dict:
    return {
        "es.nodes":             ES_NODES,
        "es.port":              ES_PORT,
        "es.resource":          index,
        "es.nodes.wan.only":    "true",
        "es.index.auto.create": "true",
        "es.batch.size.bytes":  "1mb",
        "es.batch.size.entries":"500",
        "es.batch.write.refresh":"false",
    }


def write_to_es(df, epoch_id, index: str):
    """foreachBatch writer — writes micro-batch to Elasticsearch."""
    if df.isEmpty():
        return
    (df.write
       .format("org.elasticsearch.spark.sql")
       .options(**es_options(index))
       .mode("append")
       .save())


def main():
    spark = (SparkSession.builder
             .appName("ClickstreamPipeline")
             .config("spark.streaming.stopGracefullyOnShutdown", "true")
             .config("spark.sql.streaming.checkpointLocation", CHECKPOINT_DIR)
             .getOrCreate())

    spark.sparkContext.setLogLevel("WARN")

    print(f"✓ SparkSession ready — reading from Kafka {KAFKA_SERVERS}/{KAFKA_TOPIC}")

    # ── 1. Read raw stream from Kafka ─────────────────────────────────────────
    raw = (spark.readStream
           .format("kafka")
           .option("kafka.bootstrap.servers", KAFKA_SERVERS)
           .option("subscribe", KAFKA_TOPIC)
           .option("startingOffsets", "latest")
           .option("failOnDataLoss", "false")
           .load())

    # ── 2. Parse JSON payload ─────────────────────────────────────────────────
    events = (raw
              .select(from_json(col("value").cast("string"), EVENT_SCHEMA).alias("e"))
              .select("e.*")
              .withColumn("event_time", to_timestamp(col("timestamp")))
              .withWatermark("event_time", "2 minutes"))

    # ── 3a. Raw events → ES (one doc per event) ───────────────────────────────
    raw_query = (events
                 .writeStream
                 .outputMode("append")
                 .foreachBatch(lambda df, eid: write_to_es(df, eid, "clickstream_raw"))
                 .option("checkpointLocation", f"{CHECKPOINT_DIR}/raw")
                 .trigger(processingTime="10 seconds")
                 .start())

    # ── 3b. Clicks per page (1-min tumbling window) ───────────────────────────
    page_agg = (events
                .groupBy(window("event_time", "1 minute"), col("page"))
                .agg(
                    count("*").alias("event_count"),
                    avg("duration_ms").alias("avg_duration_ms"),
                    avg("scroll_depth").alias("avg_scroll_depth"),
                )
                .select(
                    col("window.start").alias("window_start"),
                    col("window.end").alias("window_end"),
                    col("page"),
                    col("event_count"),
                    col("avg_duration_ms"),
                    col("avg_scroll_depth"),
                ))

    page_query = (page_agg
                  .writeStream
                  .outputMode("update")
                  .foreachBatch(lambda df, eid: write_to_es(df, eid, "clicks_per_page"))
                  .option("checkpointLocation", f"{CHECKPOINT_DIR}/page")
                  .trigger(processingTime="30 seconds")
                  .start())

    # ── 3c. Clicks per country ────────────────────────────────────────────────
    country_agg = (events
                   .groupBy(window("event_time", "1 minute"), col("country"))
                   .agg(
                       count("*").alias("event_count"),
                       avg("duration_ms").alias("avg_duration_ms"),
                   )
                   .select(
                       col("window.start").alias("window_start"),
                       col("window.end").alias("window_end"),
                       col("country"),
                       col("event_count"),
                       col("avg_duration_ms"),
                   ))

    country_query = (country_agg
                     .writeStream
                     .outputMode("update")
                     .foreachBatch(lambda df, eid: write_to_es(df, eid, "clicks_per_country"))
                     .option("checkpointLocation", f"{CHECKPOINT_DIR}/country")
                     .trigger(processingTime="30 seconds")
                     .start())

    # ── 3d. Clicks per device ─────────────────────────────────────────────────
    device_agg = (events
                  .groupBy(window("event_time", "1 minute"), col("device"), col("action"))
                  .agg(count("*").alias("event_count"))
                  .select(
                      col("window.start").alias("window_start"),
                      col("window.end").alias("window_end"),
                      col("device"),
                      col("action"),
                      col("event_count"),
                  ))

    device_query = (device_agg
                    .writeStream
                    .outputMode("update")
                    .foreachBatch(lambda df, eid: write_to_es(df, eid, "clicks_per_device"))
                    .option("checkpointLocation", f"{CHECKPOINT_DIR}/device")
                    .trigger(processingTime="30 seconds")
                    .start())

    print("✓ All streaming queries started. Waiting for data…")
    spark.streams.awaitAnyTermination()


if __name__ == "__main__":
    main()
