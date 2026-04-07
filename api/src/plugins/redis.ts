import fp from 'fastify-plugin'
import { FastifyPluginAsync } from 'fastify'
import Redis from 'ioredis'

declare module 'fastify' {
  interface FastifyInstance {
    redis: Redis
  }
}

const redisPlugin: FastifyPluginAsync = fp(async (app) => {
  const redis = new Redis(process.env.REDIS_URL || 'redis://redis:6379', {
    maxRetriesPerRequest: 3,
    lazyConnect: true,
    // Don't crash the process on connection errors — log and retry
    reconnectOnError: () => true
  })

  // Catch unhandled errors so they don't kill the process
  redis.on('error', (err) => {
    app.log.error({ err }, 'Redis connection error')
  })

  redis.on('connect', () => {
    app.log.info('Redis connected')
  })

  try {
    await redis.connect()
  } catch (err) {
    app.log.warn({ err }, 'Redis not available on startup — will retry automatically')
  }

  app.decorate('redis', redis)

  app.addHook('onClose', async () => {
    await redis.quit()
  })
})

export { redisPlugin }
