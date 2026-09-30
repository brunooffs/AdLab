# Chapter 3 — Redis: caching and its failure modes

## What you'll do

Find a real, currently-unresolved gap in this project's design: a Redis-backed "speed layer" that
the API reads from but that nothing writes to.

## The intended design

`api/src/routes/metrics.ts` implements `GET /v1/metrics/clicks?ad_id=...&from=...&to=...` as two
sources added together:

- **`confirmed`** — completed windows, summed from Elasticsearch's `item-click-counts` index (the
  output of the Spark job you'll meet in Chapter 5).
- **`in_progress`** — a "hot path," reading Redis keys shaped like `clicks:<ad_id>:<10-second-bucket>`
  with `mget`, meant to cover the last couple of minutes before Spark's next batch lands.

That's a real, sensible pattern — a lambda-architecture speed layer alongside a durable batch layer.

## What's actually there

```bash
docker exec -it redis redis-cli
> KEYS clicks:*
```

Empty. Nothing in this codebase — not the producer, not the Spark job, not any API route — ever
writes a `clicks:*` key. `in_progress` is always `0`. Confirm it:

```bash
curl -s 'localhost:3000/v1/metrics/clicks?ad_id=ad_x&from=0&to=9999999999' | python3 -m json.tool
```

`breakdown.in_progress` reads `0` no matter what's actually flowing through Kafka right now. The
API isn't broken — it's degrading exactly as written, just silently, since there's no error to
report. This is worth sitting with for a moment: a correctly-implemented endpoint can still give a
misleading answer if the thing it depends on was never wired up.

## Two smaller traps, while you're in here

**`redis.ts`'s reconnect option.** The plugin sets `reconnectOnError: () => true`. That name
suggests "reconnect whenever Redis errors" — but ioredis's `reconnectOnError` only fires on error
*replies* from Redis itself (like `READONLY`), not on a dropped connection, which ioredis already
retries by default regardless. Returning `true` unconditionally means it reconnects on *every* error
reply, including harmless ones. Not currently causing a problem, but not doing what its name implies
either.

**Eviction policy vs. counters.** `docker-compose.yml` runs Redis with `maxmemory-policy
allkeys-lru` — if the speed layer *were* wired up, that policy would let memory pressure evict a
click counter early, silently undercounting. A counter needs a `volatile-*` policy with TTLs, not
`allkeys-lru`.

## Try it

Set a key by hand and confirm the API would actually read it if it existed:

```bash
NOW=$(date +%s)
BUCKET=$(( (NOW / 10) * 10 ))
docker exec redis redis-cli SET "clicks:ad_test:${BUCKET}" 7
curl -s "localhost:3000/v1/metrics/clicks?ad_id=ad_test&from=$((NOW-60))&to=$((NOW+60))" | python3 -m json.tool
```

You should see `in_progress: 7`. The read path works fine — it's only the write path that's
missing. Wiring it (a small consumer that increments these keys as events arrive, or doing it
inside the Spark job's `foreachBatch`) is one of the "good first issues" in `CONTRIBUTING.md`.

## What's next

Chapter 4 is where events actually start flowing — Kafka, and the topic that both the missing Redis
writer and the very-much-present Spark job would read from.
