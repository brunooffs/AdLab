# Chapter 6 — Elasticsearch and Kibana: indexing and search

## What you'll do

Look at what Spark actually wrote, open the Kibana dashboard, and run the strongest correctness
check in this repo — `bin/e2e.sh` — properly for the first time.

```bash
./start.sh analytics
bin/setup-kibana.sh
```

## The four indices

Spark writes to four indices, one per aggregation:

```bash
curl -s 'localhost:9200/_cat/indices?v' | grep -E 'item-click|clicks-per'
```

`item-click-counts` (per ad), `clicks-per-market`, `clicks-per-adtype`, `clicks-per-campaign`. Each
document's `_id` is an MD5 hash of the aggregation key plus the window start, written with
`es.write.operation: upsert`. That's deliberate: if Spark's `foreachBatch` runs twice for the same
batch (which can happen under retry, since Kafka only guarantees *at-least-once* delivery), the
second write overwrites the first with an identical result instead of double-counting. This only
protects against Spark re-processing — it says nothing about the producer sending the same event
twice, which is a separate, still-open gap (there's no event-ID deduplication anywhere in this
pipeline, listed as a "good first issue" in `CONTRIBUTING.md`).

## A naming bug that once broke a whole dashboard

Worth knowing this actually happened, because the failure mode is instructive. Early in this
project, the Kibana dashboard's data views were titled `item-click-counts-v2`,
`clicks-per-market-v2`, and so on — a `-v2` suffix that didn't match any real index. Three panels
also aggregated on fields like `market.keyword`, a sub-field that only exists when Elasticsearch
maps a field dynamically as text; this project's index templates map those fields directly as
`keyword`, so the sub-field never existed either. The dashboard imported without error and *looked*
fine — empty panels don't throw exceptions, they just show nothing. Nothing here was corrupted;
every string was simply one character off from what actually existed. `bin/setup-kibana.sh` now
imports data views that match the real names, but it's worth remembering: a dashboard with no data
and a dashboard that's broken look identical until you check the field names by hand.

```bash
curl -s 'localhost:9200/item-click-counts/_mapping' | python3 -m json.tool | head -20
```

## Why the cluster is yellow

```bash
curl -s localhost:9200/_cluster/health | python3 -m json.tool
```

`"status": "yellow"` is expected here, not a problem to fix. Elasticsearch defaults to one replica
per index; on a single-node cluster, that replica can never be assigned anywhere (there's no second
node to put it on), so the cluster reports yellow indefinitely. Green would need either a second
node or explicit `number_of_replicas: 0` on every index — neither is worth doing for a lab.

## Running `bin/e2e.sh` properly

Everything from Chapters 4, 5, and this one comes together here. `bin/e2e.sh`:

1. creates a **throw-away Kafka topic** (so old events from your earlier experiments can't pollute
   the count),
2. starts Spark against it,
3. produces a known batch of events,
4. counts the *actual clicks in Kafka* as ground truth (the technique from Chapter 4),
5. asserts all four Elasticsearch indices sum to exactly that number,
6. checks the API's `/v1/metrics/trending` and `/v1/metrics/clicks` report the same total,
7. stops Spark cleanly and deletes the topic.

```bash
bin/e2e.sh
```

A single dropped or double-counted click fails it. This is the check this project runs after
*every* upgrade or configuration change — it's what caught real regressions during development, not
a hypothetical example. Run it now; a green run here is your proof that everything in this chapter
and the two before it is wired together correctly on your machine.

## What's next

Chapter 7 moves to the API side of the picture — specifically, what happens when a write to
Postgres is supposed to also update this same Elasticsearch data, and how much of that this project
has actually verified versus merely intended.
