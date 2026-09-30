# Chapter 9 — Observability: metrics, traces, dashboards

## What you'll do

Generate some real traffic, then watch it show up as a metric, a trace, and a dashboard panel —
three different views of the same requests.

```bash
./start.sh observability
bin/smoke.sh
```

## A metrics endpoint that used to leak memory

```bash
curl -s localhost:3000/metrics | wc -c
```

Should be a few kilobytes. Worth knowing this wasn't always true: an earlier version of this
endpoint stored every single request's duration in an array, forever, and gave every distinct URL —
including 404s to random paths — its own metric label. Under a simple test (30,000 requests, half
of them 404s to made-up paths), that endpoint's own response grew to **7.5 MB**, made up of over
90,000 separate time series, and took over half a second just to render. The current implementation
uses a real histogram library (`prom-client`) with fixed buckets and a small, bounded label set —
the same test produces a **10 KB** response with 92 series, in about 9 milliseconds. The lesson
generalizes past this one file: a metrics endpoint that records one label per distinct input value
is a memory leak with extra steps, and it's an easy mistake to make by accident.

```bash
curl -s localhost:3000/metrics | grep http_request_duration_seconds_bucket | head -3
```

## Tempo's directory trap

```bash
docker logs tempo 2>&1 | tail -5
```

If this ever shows a permission error instead of "ready," here's why it would happen, even though
it doesn't happen anymore on the current setup: Tempo's container runs as a non-root user from
version 2.6 onward, and expects to write its data under `/var/tempo` — a directory the image
pre-creates with the right ownership. An earlier version of `tempo.yml` pointed storage at `/tmp`
instead, a path that doesn't exist specially in the image; Docker would create it as a fresh,
root-owned directory on first mount, and the non-root Tempo process couldn't write to it. The fix
was moving the storage paths (and the volume mount) to `/var/tempo`. The general shape of the bug —
"this container used to run as root, now it doesn't, and a path that used to just work no longer
does" — is common enough across the whole container ecosystem to be worth recognizing on sight.

## Watch one request become a trace

```bash
curl -s localhost:3000/v1/advertisers > /dev/null
sleep 2
curl -s -G localhost:3200/api/search \
  --data-urlencode 'tags=service.name=adlab-api' --data-urlencode 'limit=3' | python3 -m json.tool
```

`api/src/tracer.ts` is imported first, before anything else, in `index.ts` — OpenTelemetry has to
patch Node's modules before the code using them loads, which is why import order here isn't
arbitrary. It auto-instruments HTTP and Redis, and `prisma.ts` adds one more span manually: a
`$use` middleware that wraps every Prisma query in its own span, tagged with the model and action.
Note the word `$use` — this middleware API is removed in Prisma 7, so upgrading Prisma past 5.x will
mean rewriting this specific piece of tracing, not just bumping a version number.

## The dashboards

Open Grafana (`localhost:3001`, `admin`/`admin`) — two dashboards are provisioned: **AdLab — API
Overview** (Kong's own metrics: request rate, p99 latency, status codes) and **AdLab — Node API**
(the API's own `prom-client` metrics: request rate by route, p50/p95/p99 latency from the real
histogram, event-loop lag, memory). Generate traffic through *both* doors and watch which dashboard
reacts:

```bash
for i in $(seq 1 20); do curl -s localhost:8000/v1/advertisers >/dev/null; done   # through Kong
for i in $(seq 1 20); do curl -s localhost:3000/v1/advertisers >/dev/null; done   # direct
```

Only the first loop shows up on the Kong dashboard — traffic that bypasses Kong is invisible to it,
same lesson as Chapter 8's rate-limit exercise, from a different angle. Both loops show up on the
Node API dashboard, since that one scrapes the API directly.

```bash
curl -s localhost:9090/api/v1/targets | python3 -c "
import json, sys
for t in json.load(sys.stdin)['data']['activeTargets']:
    print(t['labels']['job'], t['health'])
"
```

## What's next

That's the last of the "how this pipeline actually works" chapters. Chapters 10 through 12
(Kubernetes, GitOps, and CI/CD) are locked in this dashboard until the corresponding parts of this
project catch up to what the earlier chapters already prove works — check `CONTRIBUTING.md` if
you're curious what's left. Chapter 13, the capstone, is built entirely from real bugs this project
hit during development — the same ones referenced throughout this tutorial — and asks you to find
and fix one without being told which chapter it came from.
