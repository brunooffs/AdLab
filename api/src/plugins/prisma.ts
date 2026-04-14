import fp from 'fastify-plugin'
import { FastifyPluginAsync } from 'fastify'
import { PrismaClient } from '@prisma/client'
import { trace, SpanStatusCode } from '@opentelemetry/api'

declare module 'fastify' {
  interface FastifyInstance {
    prisma: PrismaClient
  }
}

const prismaPlugin: FastifyPluginAsync = fp(async (app) => {
  const prisma = new PrismaClient({
    log: ['error', 'warn'],
  })

  // ── OTel middleware — creates a span for every Prisma query ───────────────
  // @ts-ignore — $use is available but types vary by Prisma version
  prisma.$use(async (params: any, next: any) => {
    const tracer = trace.getTracer('prisma-client')
    const spanName = `prisma ${params.model ?? 'unknown'}.${params.action}`

    return tracer.startActiveSpan(spanName, async (span) => {
      span.setAttributes({
        'db.system':         'postgresql',
        'db.operation':      params.action,
        'db.sql.table':      params.model ?? '',
        'prisma.model':      params.model ?? '',
        'prisma.action':     params.action,
        'prisma.data_path':  JSON.stringify(params.dataPath ?? []),
      })

      try {
        const result = await next(params)
        span.setStatus({ code: SpanStatusCode.OK })
        return result
      } catch (err) {
        span.setStatus({ code: SpanStatusCode.ERROR, message: String(err) })
        span.recordException(err as Error)
        throw err
      } finally {
        span.end()
      }
    })
  })

  await prisma.$connect()
  app.log.info('Prisma connected to PostgreSQL')

  app.decorate('prisma', prisma)

  app.addHook('onClose', async () => {
    await prisma.$disconnect()
  })
})

export { prismaPlugin }
