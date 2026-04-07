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

import { advertisersRoutes } from './routes/advertisers'
import { campaignsRoutes }   from './routes/campaigns'
import { metricsRoutes }     from './routes/metrics'

const app = Fastify({ logger: true })

async function bootstrap() {

  await app.register(cors, { origin: true })
  await app.register(jwt, {
    secret: process.env.JWT_SECRET || 'dev-secret-change-in-production'
  })

  await app.register(swagger, {
    openapi: {
      info: { title: 'AdLab API', version: '1.0.0',
              description: 'Ad Click Aggregator — Advertiser Dashboard API' },
      servers: [{ url: 'http://localhost:8000', description: 'Via Kong (recommended)' },
                { url: 'http://localhost:3000', description: 'Direct (dev only)' }],
      components: {
        securitySchemes: {
          bearerAuth: { type: 'http', scheme: 'bearer', bearerFormat: 'JWT' }
        }
      }
    }
  })

  await app.register(swaggerUi, {
    routePrefix: '/docs',
    uiConfig: { docExpansion: 'list', deepLinking: false }
  })

  // Data layer
  await app.register(prismaPlugin)
  await app.register(redisPlugin)
  await app.register(esPlugin)
  await app.register(mongoPlugin)

  // Prometheus metrics — must register before routes
  await app.register(metricsPlugin)

  // Routes
  await app.register(advertisersRoutes, { prefix: '/v1/advertisers' })
  await app.register(campaignsRoutes,   { prefix: '/v1/campaigns' })
  await app.register(metricsRoutes,     { prefix: '/v1/metrics' })

  // GraphQL
  await app.register(graphqlPlugin)

  // Health
  app.get('/health', async () => ({
    status: 'ok',
    ts: new Date().toISOString()
  }))

  const port = Number(process.env.PORT || 3000)
  await app.listen({ port, host: '0.0.0.0' })
  app.log.info(`Direct:  http://localhost:${port}`)
  app.log.info(`Via Kong: http://localhost:8000`)
  app.log.info(`Metrics: http://localhost:${port}/metrics`)
}

bootstrap().catch(err => { console.error(err); process.exit(1) })
