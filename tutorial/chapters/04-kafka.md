# Chapter 4 — Kafka: topics, partitions, consumer groups

## What you'll do

Produce a batch of click events, watch them land in Kafka, and simulate a "viral ad" traffic
pattern using partition salting.

```bash
./start.sh streaming
./produce.sh 300 20
```

## What just happened

`produce.sh` runs the producer in its own container (Python 3.11 specifically — `kafka-python`
2.0.2 fails to import on 3.12+, one of a few version pins in this repo that exist because something
broke first). It loads a small ad catalogue from Postgres, then sends events to the `clickstream`
topic, about 1 in 6 of them a `click` (the rest are `view`s, weighted 5:1).

```bash
docker exec kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --describe --topic clickstream
```

Look at the `PartitionCount`. `docker-compose.yml` sets `KAFKA_NUM_PARTITIONS: 3` as a broker
default — but that default only applies the *first time* the topic is auto-created. If the topic
already existed with a different partition count (say, from an earlier version of this compose
file, or a volume you didn't wipe), the broker setting has no effect on it. Partition count is a
property of the topic, decided once, at creation.

## Why partitioning matters here

Kafka guarantees ordering *within* a partition, not across a topic. The producer keys each message
by `ad_id`, so all events for one ad land in the same partition and process in order relative to
each other. That's normally what you want — but it creates a specific failure mode: a "hot" ad gets
all its traffic funneled into one partition, so one consumer does all the work while the others idle.

Simulate it:

```bash
./produce.sh 2000 100 --hot-ad ad_viral_1
```

Every event for `ad_viral_1` goes to the same partition, no matter how many partitions the topic
has. The fix is salting — spreading one logical key across several partitions on purpose:

```bash
./produce.sh 2000 100 --hot-ad ad_viral_1 --buckets 4
```

Now the producer appends a random suffix (`ad_viral_1_0` through `ad_viral_1_3`) to the partition
key, spreading the hot ad's traffic across up to 4 partitions. The trade-off: anything that needs
*all* of one ad's events together (an exact global order, or a single consumer computing an
aggregate) now has to merge across partitions instead of reading one in order. There's no free
lunch here — salting fixes the hot-partition problem by creating a fan-in problem somewhere else.

## The technique `bin/e2e.sh` uses

You'll meet `bin/e2e.sh` properly in Chapter 6, but it's worth previewing one thing it does: rather
than trusting the producer's own "sent N events" output, it counts *actual clicks in Kafka itself*
as ground truth:

```bash
docker exec kafka /opt/kafka/bin/kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 --topic clickstream --from-beginning --timeout-ms 15000 \
  | python3 -c "import sys,json; print(sum(1 for l in sys.stdin if json.loads(l).get('action')=='click'))"
```

This matters because it's the only way to catch actual data loss — if you only check "did Spark
report success," you'd never notice one dropped event.

## Try it

```bash
./status.sh
```

Look at "Kafka message count (clickstream)" — this uses `kafka-get-offsets.sh`, which replaced
`GetOffsetShell` when this project upgraded to Kafka 4.x (the old tool was already removed by
Kafka 3.8; `status.sh` was silently printing nothing until that upgrade fixed it too).

## What's next

Chapter 5 is where these events get consumed — Spark Structured Streaming, and a specific,
deliberate trade-off in how this project handles (or doesn't handle) late-arriving data.
