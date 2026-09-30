# Chapter 7 — CQRS: commands, events, projections

## What you'll do

Compare the two ways this API lets you manage advertisers, and — rather than take the internals on
faith — verify one specific claim about them yourself.

## Two routes, two models

```bash
curl -s localhost:3000/docs/json | python3 -c "
import json, sys
paths = json.load(sys.stdin)['paths']
for p in sorted(paths):
    if 'advertiser' in p: print(p)
"
```

You'll see `/v1/advertisers` (classic CRUD — reads and writes both hit Postgres directly) alongside
`/v1/cqrs/advertisers` (writes go to Postgres, reads come from Elasticsearch). Same underlying data,
two different routes, on purpose — this project keeps both so you can compare them side by side.

`api/src/routes/advertisers.cqrs.ts` wires up three collaborators per request: a command handler
(writes), a query handler (reads from Elasticsearch), and a read projector — the piece meant to keep
Elasticsearch in sync after a write.

```bash
curl -s localhost:3000/v1/cqrs/advertisers/stats
```

## Being honest about what this tutorial actually verified

The command handler and read projector's *internals* — `advertiser.command.handler.ts` and
`advertiser.read.projector.ts` — describe how a Postgres write becomes an Elasticsearch document.
This tutorial doesn't assert how that wiring works, because it was never read closely enough to say
for certain whether it's a direct in-process call, an event emitter, or something else. What *is*
visible from the route file: the projector is constructed once, when the routes are registered —
not per-request — which reads like an in-process call rather than a message queue, but that's an
inference from the shape of the code, not a confirmed fact.

Rather than guess, verify it yourself:

```bash
NAME="cqrs-test-$(date +%s)"
curl -s -X POST localhost:3000/v1/cqrs/advertisers \
  -H 'Content-Type: application/json' \
  -d "{\"name\":\"$NAME\",\"email\":\"$NAME@example.com\",\"tier\":\"STANDARD\"}"
echo
curl -s "localhost:9200/advertisers/_search?q=name:$NAME"
```

If the second command finds the advertiser you just created, the projection is synchronous (or
close enough to it) that there's no visible lag. If it doesn't, wait a second and try again — that
tells you something real about the lag, and either way, you now know something this tutorial itself
didn't claim to know.

## What the routes tell you regardless of the internals

Independent of how the projection works internally, the *contract* of these routes is visible
directly in the source and worth knowing:

- A duplicate email on `POST /v1/cqrs/advertisers` returns `409`, mapped from Postgres's `P2002`
  unique-constraint error code.
- An update or delete on a non-existent advertiser returns `404`, mapped from Prisma's `P2025`
  "record not found."
- Validation (name length, valid email, tier enum) happens with Zod before any handler runs.

## What this means for `db.py`'s seeded data

Chapter 2 mentioned that the producer's seed script inserts advertisers with raw SQL, bypassing this
whole command/projection path. Now you can see exactly why that matters: those rows exist in
Postgres, and `GET /v1/advertisers` (classic CRUD, reads Postgres directly) will show them — but
`GET /v1/cqrs/advertisers` (reads only from Elasticsearch) never will, because nothing ever
projected them there. Confirm it:

```bash
docker exec postgres psql -U lab -d adlab -t -c 'SELECT name FROM "Advertiser" LIMIT 3;'
curl -s localhost:3000/v1/cqrs/advertisers | python3 -c "import json,sys; print([a['name'] for a in json.load(sys.stdin)][:3])"
```

## What's next

Chapter 8 is shorter — Kong, the one piece of this stack that sits in front of everything else you've
looked at so far, and a rate limit you can trigger in about ten seconds.
