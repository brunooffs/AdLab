# Chapter 2 — PostgreSQL and Prisma: the system of record

## What you'll do

Look at the schema Prisma manages, connect directly with `psql`, and find a real gap between what
the schema declares and what the code assumes.

```bash
docker exec -it postgres psql -U lab -d adlab
```

## The schema

`api/prisma/schema.prisma` declares two models:

```
Advertiser  — id, name, email (unique), tier (STANDARD | PREMIUM), timestamps
Campaign    — id, name, advertiserId → Advertiser, budget, dates, status, timestamps
```

Inside `psql`:

```sql
\d "Advertiser"
\d "Campaign"
SELECT COUNT(*) FROM "Advertiser";
```

If you've run `bin/smoke.sh` a few times, you'll see more rows than you expect — every run creates
a fresh advertiser and campaign. Nothing cleans them up. Harmless for a lab, but worth knowing
before you go looking for "why does trending show ads I don't recognize."

## A missing index

```sql
EXPLAIN SELECT * FROM "Campaign" WHERE "advertiserId" = (SELECT id FROM "Advertiser" LIMIT 1);
```

PostgreSQL does not automatically index foreign keys — that surprises people coming from MySQL,
where it does. `schema.prisma` has no `@@index([advertiserId])` on `Campaign`, so that query is a
sequential scan. At lab scale (a handful of rows) it doesn't matter. At real scale, every campaign
lookup for an advertiser would scan the whole table.

## Why `migrate` is its own container

Chapter 1 showed you that `api` waits for `migrate` to exit successfully. The reason this is a
*separate* container rather than a step inside `api`'s startup script: if migrations run inside the
API's own entrypoint and fail halfway, you have a partially-migrated database and a crashed API
container racing each other on retry. A dedicated one-shot job either succeeds completely or the API
never starts at all — no partial state to reason about.

```bash
docker logs migrate
```

## `db.py`'s ID assumption

The producer's `db.py` seeds sample data directly with SQL, bypassing Prisma and the API entirely —
worth knowing, since it means seeded advertisers never go through the CQRS write path in Chapter 7,
so they won't appear in the Elasticsearch-backed read model, only in Postgres. It also builds
synthetic ad IDs like this:

```python
"ad_id": f"ad_{row.campaign_id[:8]}_{j:03d}"
```

Prisma's default `cuid()` starts with a timestamp component, so the first 8 characters of two
campaign IDs created within about 36 milliseconds of each other can collide. With this project's
own seed data it never happens — but it's the kind of assumption that's silently true until it
isn't, and a good thing to notice rather than take on faith.

## Try it

```sql
SELECT id, "advertiserId", status FROM "Campaign";
```

Then check: does every campaign you see here also show up if you query the CQRS read side?

```bash
curl -s localhost:3000/v1/cqrs/advertisers | python3 -m json.tool
```

If a campaign's advertiser was seeded via `db.py` rather than through `POST /v1/cqrs/advertisers`,
you'll find it in Postgres but not here. That gap is exactly what Chapter 7 explains.

## What's next

Chapter 3 covers Redis — specifically, a part of this codebase that's *read* by the API but that
nothing in the pipeline currently *writes*.
