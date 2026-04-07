import { FastifyInstance } from 'fastify'
import { z } from 'zod'

const querySchema = z.object({
  ad_id: z.string(),
  from:  z.coerce.number(),
  to:    z.coerce.number()
})

export async function metricsRoutes(app: FastifyInstance) {

  // GET /v1/metrics/clicks?ad_id=ad_42&from=1742734800&to=1742738400
  app.get('/clicks', {
    schema: {
      tags: ['metrics'],
      summary: 'Get click counts for an ad over a time range',
      querystring: {
        type: 'object',
        required: ['ad_id', 'from', 'to'],
        properties: {
          ad_id: { type: 'string', description: 'Ad identifier' },
          from:  { type: 'number', description: 'Start timestamp (Unix seconds)' },
          to:    { type: 'number', description: 'End timestamp (Unix seconds)' }
        }
      }
    }
  }, async (req) => {
    const query = querySchema.parse(req.query)
    const now   = Math.floor(Date.now() / 1000)

    // Completed 1-min windows from Elasticsearch
    let confirmed = 0
    try {
      const esResult = await app.es.search({
        index: 'item-click-counts',
        body: {
          size: 0,
          query: {
            bool: {
              filter: [
                { term:  { ad_id: query.ad_id } },
                { range: { window_start: { gte: query.from * 1000, lte: query.to * 1000 } } }
              ]
            }
          },
          aggs: { total: { sum: { field: 'click_count' } } }
        }
      })
      confirmed = Math.round((esResult.aggregations?.total as any)?.value ?? 0)
    } catch {
      app.log.warn('ES not available — returning Redis data only')
    }

    // Hot path: partial 10-second buckets from Redis
    const keys: string[] = []
    const redisStart = Math.max(query.from, now - 120)
    for (let b = Math.floor(redisStart / 10) * 10; b <= query.to; b += 10) {
      keys.push(`clicks:${query.ad_id}:${b}`)
    }
    const vals = keys.length > 0 ? await app.redis.mget(...keys) : []
    const inProgress = vals.reduce((sum, v) => sum + (v ? parseInt(v) : 0), 0)

    return {
      ad_id:   query.ad_id,
      from:    query.from,
      to:      query.to,
      clicks:  confirmed + inProgress,
      as_of:   new Date().toISOString(),
      breakdown: { confirmed, in_progress: inProgress }
    }
  })

  // GET /v1/metrics/trending?limit=10
  app.get('/trending', {
    schema: {
      tags: ['metrics'],
      summary: 'Top N ads by clicks in the last 10 minutes',
      querystring: {
        type: 'object',
        properties: {
          limit: { type: 'number', default: 10, description: 'Number of results' }
        }
      }
    }
  }, async (req) => {
    const { limit = 10 } = req.query as any
    const tenMinAgo = new Date(Date.now() - 10 * 60 * 1000).toISOString()

    try {
      const result = await app.es.search({
        index: 'item-click-counts',
        body: {
          size: 0,
          query: { range: { window_end: { gte: tenMinAgo } } },
          aggs: {
            top_ads: {
              terms: { field: 'ad_id', size: Number(limit), order: { total: 'desc' } },
              aggs:  { total: { sum: { field: 'click_count' } } }
            }
          }
        }
      })
      const buckets = (result.aggregations?.top_ads as any)?.buckets ?? []
      return {
        as_of: new Date().toISOString(),
        ads:   buckets.map((b: any) => ({
          ad_id:  b.key,
          clicks: Math.round(b.total.value)
        }))
      }
    } catch {
      return { as_of: new Date().toISOString(), ads: [] }
    }
  })

  // GET /v1/metrics/health — quick check all data sources are reachable
  app.get('/health', {
    schema: { tags: ['metrics'], summary: 'Data source connectivity check' }
  }, async () => {
    const checks: Record<string, string> = {}

    try { await app.es.ping(); checks.elasticsearch = 'ok' }
    catch { checks.elasticsearch = 'unreachable' }

    try { await app.redis.ping(); checks.redis = 'ok' }
    catch { checks.redis = 'unreachable' }

    return { ts: new Date().toISOString(), checks }
  })
}
