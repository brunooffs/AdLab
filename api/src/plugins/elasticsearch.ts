import fp from 'fastify-plugin'
import { FastifyPluginAsync } from 'fastify'
import { Client } from '@elastic/elasticsearch'

declare module 'fastify' {
  interface FastifyInstance {
    es: Client
  }
}

const esPlugin: FastifyPluginAsync = fp(async (app) => {
  const client = new Client({ node: process.env.ES_URL || 'http://elasticsearch:9200' })
  await client.ping()
  app.decorate('es', client)
  app.log.info('Elasticsearch connected')
})

export { esPlugin }
