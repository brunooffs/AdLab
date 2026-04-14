import './tracer'   // ← must be first — OTel patches at startup

import Fastify from 'fastify'
import cors from '@fastify/cors'
import jwt from '@fastify/jwt'
import swagger from '@fastify/swagger'
import swaggerUi from '@fastify/swagger-ui'

import { prismaPlugin }   from './plugins/prisma'
import { redisPlugin }    from './plugins/redis'
import { esPlugin }       from './plugins/elasticsearch'
import { mongoPlugin }    from './plugins/mongo'
import { graphqlPlugin }  from './plugins/graphql'
import { metricsPlugin }  from './plugins/metrics'

import { advertisersRoutes }     from './routes/advertisers'
import { advertisersCqrsRoutes } from './routes/advertisers.cqrs'
import { campaignsRoutes }       from './routes/campaigns'
import { metricsRoutes }         from './routes/metrics'

const app = Fastify({ logger: true })

async function bootstrap() {

  await app.register(cors, { origin: true })
  await app.register(jwt, {
    secret: process.env.JWT_SECRET || 'dev-secret-change-in-production'
  })

  await app.register(swagger, {
    openapi: {
      info: {
        title: 'AdLab API',
        version: '1.0.0',
        description: 'Ad Click Aggregator — CQRS + Event Sourcing pattern',
      },
      servers: [
        { url: 'http://localhost:8000', description: 'Via Kong' },
        { url: 'http://localhost:3000', description: 'Direct' },
      ],
      tags: [
        { name: 'advertisers',      description: 'Classic CRUD (Postgres only)' },
        { name: 'advertisers-cqrs', description: 'CQRS pattern (writes→Postgres, reads→ES)' },
        { name: 'campaigns',        description: 'Campaign management' },
        { name: 'metrics',          description: 'Click analytics' },
      ]
    }
  })

  await app.register(swaggerUi, {
    routePrefix: '/docs',
    uiConfig: { docExpansion: 'list', deepLinking: false },
  })

  // Data layer
  await app.register(prismaPlugin)
  await app.register(redisPlugin)
  await app.register(esPlugin)
  await app.register(mongoPlugin)

  // Observability
  await app.register(metricsPlugin)

  // ── Routes ──────────────────────────────────────────────────────────────

  // Classic CRUD — original routes (Postgres read + write)
  await app.register(advertisersRoutes,     { prefix: '/v1/advertisers' })

  // CQRS pattern — separate read/write models
  // Writes → PostgreSQL → DomainEvent → ES projection
  // Reads  → Elasticsearch (fast, searchable, aggregatable)
  await app.register(advertisersCqrsRoutes, { prefix: '/v1/cqrs/advertisers' })

  await app.register(campaignsRoutes, { prefix: '/v1/campaigns' })
  await app.register(metricsRoutes,   { prefix: '/v1/metrics' })

  await app.register(graphqlPlugin)

  app.get('/health', async () => ({ status: 'ok', ts: new Date().toISOString() }))

  const port = Number(process.env.PORT || 3000)
  await app.listen({ port, host: '0.0.0.0' })

  app.log.info(`Direct:   http://localhost:${port}`)
  app.log.info(`Via Kong: http://localhost:8000`)
  app.log.info(`Docs:     http://localhost:${port}/docs`)
  app.log.info(`CQRS:     http://localhost:${port}/v1/cqrs/advertisers`)
}

bootstrap().catch(err => { console.error(err); process.exit(1) })
