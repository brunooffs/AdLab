// ─────────────────────────────────────────────────────────────────────────────
//  advertiser.queries.ts — Query side (Read Model)
//
//  Queries NEVER touch PostgreSQL — they read from Elasticsearch only.
//  ES is optimised for search, filtering, aggregations, and full-text.
//  Postgres is the source of truth but too slow for high-read scenarios.
//
//  This is the CQRS read stack:
//    HTTP GET
//      → QueryHandler reads from ES (fast, scalable)
//      → Returns denormalised view model
// ─────────────────────────────────────────────────────────────────────────────

import { Client } from '@elastic/elasticsearch'

const ES_INDEX = 'advertisers'

export interface AdvertiserViewModel {
  id:        string
  name:      string
  email:     string
  tier:      string
  createdAt: string
  campaigns: any[]
}

export class AdvertiserQueryHandler {
  constructor(private readonly es: Client) {}

  // ── List all advertisers from ES ──────────────────────────────────────────
  async findAll(params?: {
    tier?:   string
    search?: string
    from?:   number
    size?:   number
  }): Promise<{ data: AdvertiserViewModel[]; total: number }> {

    const must: any[] = []
    const filter: any[] = []

    // Full-text search across name and email
    if (params?.search) {
      must.push({
        multi_match: {
          query:  params.search,
          fields: ['name^2', 'email'],
          type:   'best_fields',
        }
      })
    }

    // Filter by tier
    if (params?.tier) {
      filter.push({ term: { 'tier.keyword': params.tier } })
    }

    const body = await this.es.search({
      index: ES_INDEX,
      from:  params?.from ?? 0,
      size:  params?.size ?? 20,
      query: {
        bool: {
          must:   must.length   ? must   : [{ match_all: {} }],
          filter: filter.length ? filter : undefined,
        }
      },
      sort: [{ createdAt: { order: 'desc' } }],
    })

    const hits = body.hits.hits
    const total = typeof body.hits.total === 'number'
      ? body.hits.total
      : body.hits.total?.value ?? 0

    return {
      data:  hits.map(h => h._source as AdvertiserViewModel),
      total,
    }
  }

  // ── Find single advertiser by ID ──────────────────────────────────────────
  async findById(id: string): Promise<AdvertiserViewModel | null> {
    try {
      const result = await this.es.get({
        index: ES_INDEX,
        id,
      })
      return result._source as AdvertiserViewModel
    } catch (err: any) {
      if (err?.meta?.statusCode === 404) return null
      throw err
    }
  }

  // ── Search advertisers (full-text) ────────────────────────────────────────
  async search(query: string): Promise<AdvertiserViewModel[]> {
    const result = await this.es.search({
      index: ES_INDEX,
      query: {
        multi_match: {
          query,
          fields: ['name^3', 'email', 'tier'],
          type:   'best_fields',
          fuzziness: 'AUTO',  // handles typos
        }
      },
      size: 10,
    })

    return result.hits.hits.map(h => h._source as AdvertiserViewModel)
  }

  // ── Aggregation — count by tier ───────────────────────────────────────────
  async countByTier(): Promise<Record<string, number>> {
    const result = await this.es.search({
      index: ES_INDEX,
      size:  0,
      aggs: {
        by_tier: {
          terms: { field: 'tier.keyword' }
        }
      }
    })

    const buckets = (result.aggregations?.by_tier as any)?.buckets ?? []
    return Object.fromEntries(
      buckets.map((b: any) => [b.key, b.doc_count])
    )
  }
}
