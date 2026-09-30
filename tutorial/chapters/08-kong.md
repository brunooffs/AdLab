# Chapter 8 — Kong: the gateway

## What you'll do

Hit the API two ways — directly, and through Kong — and trigger a rate limit on purpose.

```bash
./start.sh gateway
```

## Same API, two doors

```bash
curl -s localhost:3000/health   # direct
curl -s localhost:8000/health   # through Kong
```

Identical response. `kong.yml` declares one upstream service (`adlab-api`, pointing at
`http://api:3000`) and three routes onto it — `/v1`, `/health`, and `/docs` + `/graphql` +
`/graphiql` — each with `strip_path: false`. That flag matters more than it looks: it means Kong
forwards the path exactly as received, `/v1/advertisers` stays `/v1/advertisers` on its way to the
API. Some gateway configs strip the route prefix before forwarding; this one deliberately doesn't,
because the API's own route registration already expects the `/v1` prefix to be there.

## Trigger the rate limit

`kong.yml` attaches a `rate-limiting` plugin to the API's routes: 120 requests per minute, tracked
locally (not shared across Kong instances — fine for one gateway container, would need a different
policy in a multi-node setup).

```bash
for i in $(seq 1 130); do
  curl -s -o /dev/null -w '%{http_code}\n' localhost:8000/v1/advertisers
done | sort | uniq -c
```

Somewhere past request 120 you'll start seeing `429` instead of `200`. Run the same loop against
port `3000` (bypassing Kong entirely) and every request succeeds — the rate limit is a property of
the *gateway*, not the API itself. That's worth internalizing: an API with no rate limiting of its
own is only as protected as whatever sits in front of it, and anyone who can reach it directly
skips the limit completely.

## What else is on these routes

The same `kong.yml` also attaches `cors` (currently `origins: ["*"]` — fine for a lab, worth
tightening before this pattern goes anywhere real) and, globally, a `prometheus` plugin exposing
Kong's own request-rate, latency, and status-code metrics — which is what feeds the "AdLab — API
Overview" Grafana dashboard you'll meet properly in Chapter 9.

```bash
curl -s localhost:8001/metrics | grep kong_http_requests_total | head -3
```

Port `8001` is Kong's *admin* API — configuration and metrics, not the proxy. It's bound to
`127.0.0.1` only in this compose file, same as everything else; there's no reason it should ever be
reachable from outside your machine.

## Why `start.sh` waits for Kong specifically

Every other service in this stack that `start.sh` waits on is waited for via Docker's own
`healthcheck` mechanism (`condition: service_healthy` in `depends_on`). Kong gets an *extra*,
separate wait loop in `start.sh` itself, polling `localhost:8000/health` after everything else is
up. The reason: Kong's own healthcheck reports healthy once Kong's process is running, which can be
slightly before it's finished picking up its declarative config and is actually able to proxy
requests. The gap is small — a second or two — but real enough that an early `bin/smoke.sh` run
against Kong could see a connection refused. The extra wait exists because that flakiness was
observed, not as a precaution against something hypothetical.

## Why this Kong version, specifically

`docker-compose.yml` pins `kong:3.9.3-ubuntu`. As of this project's last check, that's the newest
open-source image Kong publishes — the project's open-source Docker images stopped being published
past the 3.9 line. It still receives patches within that line, which is why it's pinned to a patch
version rather than just `3.9`.

## What's next

Chapter 9 pulls together everything you've poked at with `curl` so far — metrics, traces, and the
two Grafana dashboards this project ships — into one place you can actually watch live.
