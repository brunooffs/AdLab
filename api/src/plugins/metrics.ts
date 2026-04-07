import fp from 'fastify-plugin'
import { FastifyPluginAsync } from 'fastify'

// Simple Prometheus metrics without external lib
// For production use @fastify/metrics or prom-client

interface Counter { [key: string]: number }
interface Histogram { [key: string]: number[] }

const counters: Counter = {}
const histograms: Histogram = {}
const startTime = Date.now()

function inc(name: string, labels: Record<string, string> = {}) {
  const key = name + JSON.stringify(labels)
  counters[key] = (counters[key] || 0) + 1
}

function observe(name: string, value: number, labels: Record<string, string> = {}) {
  const key = name + JSON.stringify(labels)
  if (!histograms[key]) histograms[key] = []
  histograms[key].push(value)
}

export function recordRequest(method: string, route: string, status: number, durationMs: number) {
  inc('http_requests_total', { method, route, status: String(status) })
  observe('http_request_duration_ms', durationMs, { method, route })
}

function renderMetrics(): string {
  const lines: string[] = []
  const uptime = (Date.now() - startTime) / 1000

  lines.push('# HELP process_uptime_seconds API uptime in seconds')
  lines.push('# TYPE process_uptime_seconds gauge')
  lines.push(`process_uptime_seconds ${uptime.toFixed(2)}`)

  lines.push('# HELP http_requests_total Total HTTP requests')
  lines.push('# TYPE http_requests_total counter')
  for (const [key, val] of Object.entries(counters)) {
    const name = key.split('{')[0]
    const labelsStr = key.slice(name.length)
    try {
      const labels = JSON.parse(labelsStr)
      const labelParts = Object.entries(labels).map(([k, v]) => `${k}="${v}"`).join(',')
      lines.push(`${name}{${labelParts}} ${val}`)
    } catch { lines.push(`${name} ${val}`) }
  }

  lines.push('# HELP http_request_duration_ms HTTP request duration in ms')
  lines.push('# TYPE http_request_duration_ms histogram')
  for (const [key, vals] of Object.entries(histograms)) {
    if (vals.length === 0) continue
    const name = key.split('{')[0]
    const labelsStr = key.slice(name.length)
    const sorted = [...vals].sort((a, b) => a - b)
    const sum = sorted.reduce((a, b) => a + b, 0)
    const p50 = sorted[Math.floor(sorted.length * 0.5)] || 0
    const p95 = sorted[Math.floor(sorted.length * 0.95)] || 0
    const p99 = sorted[Math.floor(sorted.length * 0.99)] || 0
    try {
      const labels = JSON.parse(labelsStr)
      const lp = Object.entries(labels).map(([k, v]) => `${k}="${v}"`).join(',')
      lines.push(`${name}_p50_ms{${lp}} ${p50.toFixed(2)}`)
      lines.push(`${name}_p95_ms{${lp}} ${p95.toFixed(2)}`)
      lines.push(`${name}_p99_ms{${lp}} ${p99.toFixed(2)}`)
      lines.push(`${name}_sum{${lp}} ${sum.toFixed(2)}`)
      lines.push(`${name}_count{${lp}} ${sorted.length}`)
    } catch { /* skip malformed */ }
  }

  return lines.join('\n') + '\n'
}

const metricsPlugin: FastifyPluginAsync = fp(async (app) => {

  // Hook — record every request
  app.addHook('onResponse', async (req, reply) => {
    const duration = reply.elapsedTime
    const route = req.routerPath || req.url
    recordRequest(req.method, route, reply.statusCode, duration)
  })

  // GET /metrics — Prometheus scrape endpoint
  app.get('/metrics', {
    schema: { hide: true }  // hide from Swagger
  }, async (_req, reply) => {
    reply.header('Content-Type', 'text/plain; version=0.0.4; charset=utf-8')
    return reply.send(renderMetrics())
  })

  app.log.info('Metrics endpoint ready at /metrics')
})

export { metricsPlugin }

