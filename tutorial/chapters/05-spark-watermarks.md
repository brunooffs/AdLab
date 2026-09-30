# Chapter 5 — Spark Structured Streaming: watermarks

## What you'll do

Run the aggregation job, watch it recover from a killed executor without your help, and understand
a trade-off this project makes deliberately: no watermark.

```bash
./spark.sh
```

Leave this running in its own terminal — it stays in the foreground until you stop it.

## What "no watermark" means

`spark-jobs/adclick_streaming.py` reads from Kafka, groups click events into one-minute tumbling
windows, and writes aggregates to Elasticsearch — but it does this in **complete output mode with
no watermark**. Two consequences, and they're linked:

- **Replaying historical data works correctly.** A watermark tells Spark "I'll assume no more data
  will arrive for a window once we're this far past it," which is exactly the assumption that
  breaks if you ever replay a topic from the beginning (`--from-beginning`, or `startingOffsets:
  earliest`, which this job uses). With no watermark, an event from an hour ago still updates its
  window correctly no matter when it's processed.
- **State grows without bound.** Every window Spark has ever seen stays in memory, because nothing
  ever tells it a window is "done" and safe to forget. Complete mode then rewrites *every* window,
  old and new, to Elasticsearch on every trigger (every 30 seconds here) — not just the ones that
  changed.

This is a real trade-off, not an oversight — correctness-under-replay versus bounded memory. A
production system processing a live, non-replayed stream would very likely use `update` mode with a
watermark instead, matching the original design spec in `docs/ad-click-aggregator-schemas.docx`
(a 10-second trigger, a 10-second watermark). Try it yourself later: the trade-off only shows up
after hours of continuous running, which is longer than one lab session — but you now know what to
watch for (`docker stats spark-master` creeping upward over time).

## Watch it recover from a killed executor

```bash
docker exec spark-master ps aux | grep CoarseGrainedExecutorBackend
```

Find the executor's PID and kill it:

```bash
docker exec spark-master kill -9 <pid>
```

Watch the `./spark.sh` terminal and the Spark master UI at http://localhost:8081. Within a couple
of minutes you should see the master detect the lost executor (a heartbeat-timeout message) and
launch a replacement — this exact recovery happened for real during this project's own upgrade
work, unprompted, and the pipeline picked back up processing new events once the new executor
registered. You don't need to do anything; that's the point of the exercise.

## The stoppable runner

`./spark.sh` normally blocks until you press Ctrl+C, which is inconvenient for anything scripted.
`spark-jobs/adclick_runner.py` wraps the same job with two optional stop conditions:

```bash
SPARK_APP=adclick_runner.py RUN_SECONDS=60 ./spark.sh
```

This runs for 60 seconds and stops itself cleanly — calling `.stop()` on every active streaming
query rather than killing the process. `bin/e2e.sh` uses this (with a `STOP_FILE` instead of a time
limit) to run Spark unattended as part of an automated check.

## Try it

```bash
./produce.sh 300 20
```

While `spark.sh` is running, watch its terminal print `Wrote batch N to <index>` roughly every 30
seconds. Then:

```bash
curl -s 'localhost:9200/item-click-counts/_search?size=0' \
  -H 'Content-Type: application/json' \
  -d '{"aggs":{"t":{"sum":{"field":"click_count"}}}}'
```

## What's next

Chapter 6 picks up exactly where this left off — what Elasticsearch does with what Spark just wrote,
and a real naming bug that once made an entire Kibana dashboard look broken for no visible reason.
