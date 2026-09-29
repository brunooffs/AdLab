"""
adclick_streaming.py — AdLab Clickstream Pipeline
Processes ad click events from Kafka → Elasticsearch.
No watermark — works correctly when replaying historical events.
"""

import json
import os
import urllib.request
import urllib.error

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql.functions import (
    approx_count_distinct, avg, col, concat_ws,
    count, from_json, md5, to_timestamp, window,
)
from pyspark.sql.types import (
    IntegerType, LongType, StringType,
    StructField, StructType,
)

# ── Config ────────────────────────────────────────────────────────────────────
KAFKA_SERVERS  = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
KAFKA_TOPIC    = os.getenv("KAFKA_TOPIC",             "clickstream")
ES_NODES       = os.getenv("ES_NODES",                "elasticsearch")
ES_PORT        = os.getenv("ES_PORT",                 "9200")
CHECKPOINT_DIR = os.getenv("CHECKPOINT_DIR",          "/tmp/spark-checkpoints")
WINDOW_DUR     = os.getenv("WINDOW_DURATION",         "1 minute")
TRIGGER        = os.getenv("TRIGGER_INTERVAL",        "30 seconds")

ES_BASE_URL    = f"http://{ES_NODES}:{ES_PORT}"

# ── Event schema ──────────────────────────────────────────────────────────────
EVENT_SCHEMA = StructType([
    StructField("event_id",      StringType(),  True),
    StructField("user_id",       StringType(),  True),
    StructField("session_id",    StringType(),  True),
    StructField("ad_id",         StringType(),  True),
    StructField("advertiser_id", StringType(),  True),
    StructField("campaign_id",   StringType(),  True),
    StructField("ad_type",       StringType(),  True),
    StructField("market",        StringType(),  True),
    StructField("action",        StringType(),  True),
    StructField("timestamp",     LongType(),    True),
    StructField("ingest_time",   LongType(),    True),
    StructField("rank",          IntegerType(), True),
    StructField("page_url",      StringType(),  True),
])


# ── ES helpers ────────────────────────────────────────────────────────────────
def _es_put(path: str, body: dict) -> None:
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{ES_BASE_URL}/{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="PUT",
    )
    try:
        urllib.request.urlopen(req, timeout=10)
    except urllib.error.HTTPError as e:
        if e.code != 400:
            print(f"  WARNING: ES PUT /{path} returned {e.code}")
    except Exception as e:
        print(f"  WARNING: ES PUT /{path} failed: {e}")


def create_es_templates() -> None:
    print("Creating ES index templates...")
    _es_put("_index_template/adlab-click-counts", {
        "index_patterns": ["item-click-counts*"],
        "priority": 100,
        "template": {"mappings": {"properties": {
            "window_start":  {"type": "date"},
            "window_end":    {"type": "date"},
            "ad_id":         {"type": "keyword"},
            "advertiser_id": {"type": "keyword"},
            "click_count":   {"type": "long"},
            "unique_users":  {"type": "long"},
            "avg_rank":      {"type": "float"},
            "doc_id":        {"type": "keyword"},
        }}}
    })
    _es_put("_index_template/adlab-clicks-market", {
        "index_patterns": ["clicks-per-market*"],
        "priority": 100,
        "template": {"mappings": {"properties": {
            "window_start": {"type": "date"},
            "window_end":   {"type": "date"},
            "market":       {"type": "keyword"},
            "click_count":  {"type": "long"},
            "doc_id":       {"type": "keyword"},
        }}}
    })
    _es_put("_index_template/adlab-clicks-adtype", {
        "index_patterns": ["clicks-per-adtype*"],
        "priority": 100,
        "template": {"mappings": {"properties": {
            "window_start": {"type": "date"},
            "window_end":   {"type": "date"},
            "ad_type":      {"type": "keyword"},
            "click_count":  {"type": "long"},
            "doc_id":       {"type": "keyword"},
        }}}
    })
    _es_put("_index_template/adlab-clicks-campaign", {
        "index_patterns": ["clicks-per-campaign*"],
        "priority": 100,
        "template": {"mappings": {"properties": {
            "window_start":  {"type": "date"},
            "window_end":    {"type": "date"},
            "campaign_id":   {"type": "keyword"},
            "advertiser_id": {"type": "keyword"},
            "click_count":   {"type": "long"},
            "unique_users":  {"type": "long"},
            "doc_id":        {"type": "keyword"},
        }}}
    })
    print("  ES templates ready")


def delete_old_indices() -> None:
    for index in ["item-click-counts", "clicks-per-market",
                  "clicks-per-adtype", "clicks-per-campaign"]:
        req = urllib.request.Request(
            f"{ES_BASE_URL}/{index}", method="DELETE")
        try:
            urllib.request.urlopen(req, timeout=10)
            print(f"  Deleted old index: {index}")
        except urllib.error.HTTPError as e:
            if e.code != 404:
                print(f"  WARNING: could not delete {index}: {e.code}")
        except Exception:
            pass


# ── Spark helpers ─────────────────────────────────────────────────────────────
def add_doc_id(df: DataFrame, *key_cols: str) -> DataFrame:
    return df.withColumn(
        "doc_id", md5(concat_ws("_", *[col(c) for c in key_cols]))
    )


def write_to_es(df: DataFrame, epoch_id: int, index: str) -> None:
    if df.rdd.isEmpty():
        return
    (df.write
       .format("org.elasticsearch.spark.sql")
       .option("es.nodes",               ES_NODES)
       .option("es.port",                ES_PORT)
       .option("es.resource",            index)
       .option("es.nodes.wan.only",      "true")
       .option("es.index.auto.create",   "true")
       .option("es.write.operation",     "upsert")
       .option("es.mapping.id",          "doc_id")
       .option("es.batch.size.bytes",    "1mb")
       .option("es.batch.write.refresh", "false")
       .mode("append")
       .save())
    print(f"  Wrote batch {epoch_id} to {index}")


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    spark = (
        SparkSession.builder
        .appName("AdClickStreaming")
        .config("spark.streaming.stopGracefullyOnShutdown", "true")
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")

    print("\n" + "="*60)
    print("AdLab Clickstream Pipeline — starting")
    print("="*60 + "\n")

    create_es_templates()
    delete_old_indices()

    print(f"Kafka:  {KAFKA_SERVERS} → {KAFKA_TOPIC}")
    print(f"ES:     {ES_BASE_URL}")
    print(f"Window: {WINDOW_DUR} | Trigger: {TRIGGER}")
    print("Watermark: NONE (replaying historical events)\n")

    # ── Read from Kafka ───────────────────────────────────────────────────────
    raw = (
        spark.readStream
        .format("kafka")
        .option("kafka.bootstrap.servers", KAFKA_SERVERS)
        .option("subscribe",               KAFKA_TOPIC)
        .option("startingOffsets",         "earliest")
        .option("failOnDataLoss",          "false")
        .load()
    )

    # ── Parse events — NO watermark so historical events are not dropped ──────
    events = (
        raw
        .select(from_json(col("value").cast("string"), EVENT_SCHEMA).alias("e"))
        .select("e.*")
        .withColumn("event_time", to_timestamp(col("timestamp") / 1000))
    )

    clicks = events.filter(col("action") == "click")

    # ── clicks per ad ─────────────────────────────────────────────────────────
    q1 = (
        add_doc_id(
            clicks
            .groupBy(window("event_time", WINDOW_DUR), col("ad_id"), col("advertiser_id"))
            .agg(
                count("*").alias("click_count"),
                approx_count_distinct("user_id").alias("unique_users"),
                avg("rank").alias("avg_rank"),
            )
            .select(
                col("window.start").alias("window_start"),
                col("window.end").alias("window_end"),
                col("ad_id"), col("advertiser_id"),
                col("click_count"), col("unique_users"), col("avg_rank"),
            ),
            "ad_id", "window_start"
        )
        .writeStream
        .outputMode("complete")
        .foreachBatch(lambda df, eid: write_to_es(df, eid, "item-click-counts"))
        .option("checkpointLocation", f"{CHECKPOINT_DIR}/item-click-counts")
        .trigger(processingTime=TRIGGER)
        .start()
    )

    # ── clicks per market ─────────────────────────────────────────────────────
    q2 = (
        add_doc_id(
            clicks
            .groupBy(window("event_time", WINDOW_DUR), col("market"))
            .agg(count("*").alias("click_count"))
            .select(
                col("window.start").alias("window_start"),
                col("window.end").alias("window_end"),
                col("market"), col("click_count"),
            ),
            "market", "window_start"
        )
        .writeStream
        .outputMode("complete")
        .foreachBatch(lambda df, eid: write_to_es(df, eid, "clicks-per-market"))
        .option("checkpointLocation", f"{CHECKPOINT_DIR}/clicks-per-market")
        .trigger(processingTime=TRIGGER)
        .start()
    )

    # ── clicks per ad type ────────────────────────────────────────────────────
    q3 = (
        add_doc_id(
            clicks
            .groupBy(window("event_time", WINDOW_DUR), col("ad_type"))
            .agg(count("*").alias("click_count"))
            .select(
                col("window.start").alias("window_start"),
                col("window.end").alias("window_end"),
                col("ad_type"), col("click_count"),
            ),
            "ad_type", "window_start"
        )
        .writeStream
        .outputMode("complete")
        .foreachBatch(lambda df, eid: write_to_es(df, eid, "clicks-per-adtype"))
        .option("checkpointLocation", f"{CHECKPOINT_DIR}/clicks-per-adtype")
        .trigger(processingTime=TRIGGER)
        .start()
    )

    # ── clicks per campaign ───────────────────────────────────────────────────
    q4 = (
        add_doc_id(
            clicks
            .groupBy(window("event_time", WINDOW_DUR), col("campaign_id"), col("advertiser_id"))
            .agg(
                count("*").alias("click_count"),
                approx_count_distinct("user_id").alias("unique_users"),
            )
            .select(
                col("window.start").alias("window_start"),
                col("window.end").alias("window_end"),
                col("campaign_id"), col("advertiser_id"),
                col("click_count"), col("unique_users"),
            ),
            "campaign_id", "window_start"
        )
        .writeStream
        .outputMode("complete")
        .foreachBatch(lambda df, eid: write_to_es(df, eid, "clicks-per-campaign"))
        .option("checkpointLocation", f"{CHECKPOINT_DIR}/clicks-per-campaign")
        .trigger(processingTime=TRIGGER)
        .start()
    )

    print("4 streaming queries running:")
    print("  item-click-counts | clicks-per-market | clicks-per-adtype | clicks-per-campaign")
    print(f"  Trigger: {TRIGGER} | Press Ctrl+C to stop\n")

    spark.streams.awaitAnyTermination()


if __name__ == "__main__":
    main()
