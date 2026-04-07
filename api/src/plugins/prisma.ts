import fp from 'fastify-plugin'
import { FastifyPluginAsync } from 'fastify'
import { PrismaClient } from '@prisma/client'

declare module 'fastify' {
  interface FastifyInstance {
    prisma: PrismaClient
  }
}

const prismaPlugin: FastifyPluginAsync = fp(async (app) => {
  const prisma = new PrismaClient({ log: ['error', 'warn'] })
  await prisma.$connect()
  app.decorate('prisma', prisma)
  app.addHook('onClose', async () => { await prisma.$disconnect() })
  app.log.info('Prisma connected to PostgreSQL')
})

export { prismaPlugin }
