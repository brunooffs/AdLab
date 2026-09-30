// ─────────────────────────────────────────────────────────────────────────────
//  metrics.test.ts — regression test for a real bug this project shipped and
//  fixed once already: the original hand-rolled /metrics implementation kept
//  every request duration forever and gave every distinct URL — including
//  404s to random/scanned paths — its own label. Under 30,000 requests, half
//  of them 404s, that endpoint's own response grew to 7.5 MB across 90,007
//  time series. The current implementation (prom-client, matched-route
//  labels only) produces ~10 KB and 92 series under the same load.
//
//  This test doesn't re-run that full scale (too slow for CI on every push);
//  it runs a much smaller version of the same shape and asserts the two
//  properties that actually matter: the response stays small, and the
//  cardinality of the `route` label stays bounded regardless of how many
//  distinct unmatched paths are hit. If either regresses, this fails.
// ─────────────────────────────────────────────────────────────────────────────
import { test } from 'node:test'
import assert from 'node:assert/strict'
import Fastify from 'fastify'
import { metricsPlugin } from '../src/plugins/metrics'

async function buildApp() {
  const app = Fastify()
  await app.register(metricsPlugin)
  app.get('/v1/advertisers/:id', async (req) => ({ id: (req.params as any).id }))
  return app
}

test('metrics: unmatched routes share one label, not one-per-URL', async () => {
  const app = await buildApp()

  // 200 requests to 200 DISTINCT, never-repeated paths — exactly the shape
  // that broke the old implementation (a scanner or a typo generator).
  for (let i = 0; i < 200; i++) {
    await app.inject({ method: 'GET', url: `/scan/${i}/${Math.random().toString(36).slice(2)}` })
  }

  const res = await app.inject({ method: 'GET', url: '/metrics' })
  const body = res.body

  const routeLabels = new Set([...body.matchAll(/route="([^"]*)"/g)].map((m) => m[1]))
  assert.equal(
    routeLabels.size, 1,
    `expected exactly one route label ("unmatched") for 200 distinct 404s, got ${routeLabels.size}: ${[...routeLabels].slice(0, 5)}`
  )
  assert.ok(routeLabels.has('unmatched'), 'the shared label should be "unmatched"')

  await app.close()
})

test('metrics: response size stays bounded under repeated load', async () => {
  const app = await buildApp()

  for (let i = 0; i < 500; i++) {
    await app.inject({ method: 'GET', url: `/v1/advertisers/id_${i}` })
    await app.inject({ method: 'GET', url: `/nope/${i}` })
  }

  const res = await app.inject({ method: 'GET', url: '/metrics' })
  // The old implementation crossed 7.5MB at 30k requests (15k per route
  // shape). 1000 requests here should stay under 50KB by a wide margin if
  // cardinality is actually bounded; the old code would already be well
  // into six figures of bytes at this volume.
  assert.ok(
    res.body.length < 50_000,
    `metrics response is ${res.body.length} bytes — expected well under 50KB; this usually means a label became unbounded again`
  )

  await app.close()
})

test('metrics: real histogram buckets exist (not just precomputed percentiles)', async () => {
  const app = await buildApp()
  await app.inject({ method: 'GET', url: '/v1/advertisers/x' })

  const res = await app.inject({ method: 'GET', url: '/metrics' })
  assert.match(
    res.body, /^http_request_duration_seconds_bucket\{.*le="\+Inf".*\}/m,
    'expected a real cumulative histogram (le="+Inf" bucket) — needed for histogram_quantile() across replicas'
  )

  await app.close()
})

test('metrics: Content-Type matches what Prometheus expects', async () => {
  const app = await buildApp()
  const res = await app.inject({ method: 'GET', url: '/metrics' })
  assert.match(res.headers['content-type'] as string, /^text\/plain/)
  await app.close()
})
