import fp from 'fastify-plugin'
import { FastifyPluginAsync } from 'fastify'
import mercurius from 'mercurius'

const schema = `
  type Advertiser {
    id: ID!
    name: String!
    email: String!
    tier: String!
    createdAt: String!
    campaigns: [Campaign!]!
  }

  type Campaign {
    id: ID!
    name: String!
    budget: Float!
    status: String!
    startDate: String!
    endDate: String
  }

  type ClickMetric {
    adId: String!
    clicks: Int!
    asOf: String!
    confirmed: Int!
    inProgress: Int!
  }

  type TrendingAd {
    adId: String!
    clicks: Int!
  }

  type Query {
    advertisers: [Advertiser!]!
    advertiser(id: ID!): Advertiser
    campaigns(advertiserId: ID!): [Campaign!]!
    clickMetrics(adId: String!, from: Int!, to: Int!): ClickMetric!
    trending(limit: Int): [TrendingAd!]!
  }
`

const resolvers = {
  Query: {
    advertisers: async (_: any, __: any, { app }: any) => {
      return app.prisma.advertiser.findMany({ include: { campaigns: true } })
    },

    advertiser: async (_: any, { id }: any, { app }: any) => {
      return app.prisma.advertiser.findUnique({
        where: { id },
        include: { campaigns: true }
      })
    },

    campaigns: async (_: any, { advertiserId }: any, { app }: any) => {
      return app.prisma.campaign.findMany({ where: { advertiserId } })
    },

    clickMetrics: async (_: any, { adId, from, to }: any, { app }: any) => {
      const now = Math.floor(Date.now() / 1000)

      // ES: completed windows
      const esResult = await app.es.search({
        index: 'item-click-counts',
        body: {
          size: 0,
          query: {
            bool: {
              filter: [
                { term: { ad_id: adId } },
                { range: { window_start: { gte: from * 1000, lte: to * 1000 } } }
              ]
            }
          },
          aggs: { total: { sum: { field: 'click_count' } } }
        }
      })
      const confirmed = Math.round((esResult.aggregations?.total as any)?.value ?? 0)

      // Redis: hot path buckets
      const keys: string[] = []
      const redisStart = Math.max(from, now - 120)
      for (let b = Math.floor(redisStart / 10) * 10; b <= to; b += 10) {
        keys.push(`clicks:${adId}:${b}`)
      }
      const vals = keys.length > 0 ? await app.redis.mget(...keys) : []
      const inProgress = vals.reduce((sum: number, v: string | null) => sum + (v ? parseInt(v) : 0), 0)

      return {
        adId,
        clicks: confirmed + inProgress,
        asOf: new Date().toISOString(),
        confirmed,
        inProgress
      }
    },

    trending: async (_: any, { limit = 10 }: any, { app }: any) => {
      const tenMinAgo = new Date(Date.now() - 10 * 60 * 1000).toISOString()
      const result = await app.es.search({
        index: 'item-click-counts',
        body: {
          size: 0,
          query: { range: { window_end: { gte: tenMinAgo } } },
          aggs: {
            top_ads: {
              terms: { field: 'ad_id', size: limit, order: { total: 'desc' } },
              aggs: { total: { sum: { field: 'click_count' } } }
            }
          }
        }
      })
      const buckets = (result.aggregations?.top_ads as any)?.buckets ?? []
      return buckets.map((b: any) => ({
        adId: b.key,
        clicks: Math.round(b.total.value)
      }))
    }
  }
}

const graphqlPlugin: FastifyPluginAsync = fp(async (app) => {
  await app.register(mercurius, {
    schema,
    resolvers,
    context: () => ({ app }),
    graphiql: true   // GraphQL IDE at /graphiql
  })
  app.log.info('GraphQL ready at /graphql — IDE at /graphiql')
})

export { graphqlPlugin }
