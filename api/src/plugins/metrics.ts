import fp from 'fastify-plugin'
import { FastifyPluginAsync } from 'fastify'
import { Registry, Counter, Histogram, collectDefaultMetrics } from 'prom-client'

// One registry per process. collectDefaultMetrics adds the Node.js runtime metrics
// (event-loop lag, heap, GC, CPU, open handles, process start time, ...).
const register = new Registry()
collectDefaultMetrics({ register })

const httpRequests = new Counter({
  name: 'http_requests_total',
  help: 'Total HTTP requests',
  labelNames: ['method', 'route', 'status'] as const,
  registers: [register],
})

// A real histogram: cumulative buckets that Prometheus can aggregate across
// replicas with histogram_quantile(). Memory use is constant, however many
// requests are served.
const httpDuration = new Histogram({
  name: 'http_request_duration_seconds',
  help: 'HTTP request duration in seconds',
  labelNames: ['method', 'route', 'status'] as const,
  buckets: [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10],
  registers: [register],
})

// Same signature as before (duration in ms) so existing callers keep working.
export function recordRequest(method: string, route: string, status: number, durationMs: number) {
  const labels = { method, route, status: String(status) }
  httpRequests.inc(labels)
  httpDuration.observe(labels, durationMs / 1000)
}

const metricsPlugin: FastifyPluginAsync = fp(async (app) => {

  app.addHook('onResponse', async (req, reply) => {
    // routeOptions.url is the route pattern (/v1/advertisers/:id), which keeps the
    // label set small. Unmatched URLs (404s) share one fixed label: using req.url
    // would create a new time series for every distinct path a scanner or typo sends.
    const route = req.routeOptions?.url ?? 'unmatched'
    recordRequest(req.method, route, reply.statusCode, reply.elapsedTime)
  })

  app.get('/metrics', {
    schema: { hide: true }
  }, async (_req, reply) => {
    reply.header('Content-Type', register.contentType)
    return reply.send(await register.metrics())
  })

  app.log.info('Metrics endpoint ready at /metrics')
})

export { metricsPlugin }
