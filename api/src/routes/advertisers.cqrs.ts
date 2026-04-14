// ─────────────────────────────────────────────────────────────────────────────
//  advertisers.cqrs.ts — CQRS-based advertiser routes
//
//  GET  routes → AdvertiserQueryHandler  (reads from Elasticsearch)
//  POST/PATCH/DELETE routes → AdvertiserCommandHandler (writes to PostgreSQL)
//
//  The route layer only knows about Commands and Queries — it has no direct
//  knowledge of Prisma or Elasticsearch. This is the key CQRS separation.
// ─────────────────────────────────────────────────────────────────────────────

import { FastifyInstance } from 'fastify'
import { z } from 'zod'
import { AdvertiserCommandHandler } from '../handlers/advertiser.command.handler'
import { AdvertiserQueryHandler }   from '../queries/advertiser.queries'
import { AdvertiserReadProjector }  from '../handlers/advertiser.read.projector'

// ── Validation schemas ────────────────────────────────────────────────────────
const createSchema = z.object({
  name:  z.string().min(1).max(100),
  email: z.string().email(),
  tier:  z.enum(['STANDARD', 'PREMIUM']).default('STANDARD'),
})

const updateSchema = createSchema.partial()

export async function advertisersCqrsRoutes(app: FastifyInstance) {

  // Initialise CQRS handlers
  const commandHandler = new AdvertiserCommandHandler(app.prisma)
  const queryHandler   = new AdvertiserQueryHandler(app.es)

  // Initialise read model projector — subscribes to domain events
  // and syncs changes from Postgres → Elasticsearch automatically
  new AdvertiserReadProjector(app.es)

  // ── QUERIES (reads from Elasticsearch) ──────────────────────────────────

  // GET /v1/advertisers?search=...&tier=PREMIUM
  app.get('/', {
    schema: {
      tags: ['advertisers-cqrs'],
      summary: '[CQRS Query] List advertisers from Elasticsearch',
      querystring: {
        type: 'object',
        properties: {
          search: { type: 'string', description: 'Full-text search' },
          tier:   { type: 'string', enum: ['STANDARD', 'PREMIUM'] },
          from:   { type: 'integer', default: 0 },
          size:   { type: 'integer', default: 20 },
        }
      }
    }
  }, async (req) => {
    const { search, tier, from, size } = req.query as any
    return queryHandler.findAll({ search, tier, from, size })
  })

  // GET /v1/advertisers/search?q=...
  app.get('/search', {
    schema: {
      tags: ['advertisers-cqrs'],
      summary: '[CQRS Query] Full-text search with fuzzy matching',
      querystring: {
        type: 'object',
        required: ['q'],
        properties: {
          q: { type: 'string' }
        }
      }
    }
  }, async (req) => {
    const { q } = req.query as { q: string }
    return queryHandler.search(q)
  })

  // GET /v1/advertisers/stats
  app.get('/stats', {
    schema: {
      tags: ['advertisers-cqrs'],
      summary: '[CQRS Query] Aggregation stats from Elasticsearch',
    }
  }, async () => {
    return queryHandler.countByTier()
  })

  // GET /v1/advertisers/:id
  app.get('/:id', {
    schema: {
      tags: ['advertisers-cqrs'],
      summary: '[CQRS Query] Get advertiser by ID from Elasticsearch',
    }
  }, async (req, reply) => {
    const { id } = req.params as { id: string }
    const advertiser = await queryHandler.findById(id)
    if (!advertiser) return reply.status(404).send({ error: 'Not found' })
    return advertiser
  })

  // ── COMMANDS (writes to PostgreSQL) ─────────────────────────────────────

  // POST /v1/advertisers
  app.post('/', {
    schema: {
      tags: ['advertisers-cqrs'],
      summary: '[CQRS Command] Create advertiser → Postgres + ES projection',
      body: {
        type: 'object',
        required: ['name', 'email'],
        properties: {
          name:  { type: 'string' },
          email: { type: 'string' },
          tier:  { type: 'string', enum: ['STANDARD', 'PREMIUM'] },
        }
      }
    }
  }, async (req, reply) => {
    const body = createSchema.parse(req.body)
    try {
      const result = await commandHandler.handle({
        type:    'CREATE_ADVERTISER',
        payload: body,
      })
      return reply.status(201).send(result)
    } catch (err: any) {
      if (err.code === 'P2002') {
        return reply.status(409).send({ error: 'Email already exists' })
      }
      throw err
    }
  })

  // PATCH /v1/advertisers/:id
  app.patch('/:id', {
    schema: {
      tags: ['advertisers-cqrs'],
      summary: '[CQRS Command] Update advertiser → Postgres + ES projection',
    }
  }, async (req, reply) => {
    const { id } = req.params as { id: string }
    const body = updateSchema.parse(req.body)
    try {
      const result = await commandHandler.handle({
        type:    'UPDATE_ADVERTISER',
        payload: { id, ...body },
      })
      return result
    } catch (err: any) {
      if (err.code === 'P2025') {
        return reply.status(404).send({ error: 'Advertiser not found' })
      }
      throw err
    }
  })

  // DELETE /v1/advertisers/:id
  app.delete('/:id', {
    schema: {
      tags: ['advertisers-cqrs'],
      summary: '[CQRS Command] Delete advertiser → Postgres + ES projection',
    }
  }, async (req, reply) => {
    const { id } = req.params as { id: string }
    try {
      await commandHandler.handle({
        type:    'DELETE_ADVERTISER',
        payload: { id },
      })
      return reply.status(204).send()
    } catch (err: any) {
      if (err.code === 'P2025') {
        return reply.status(404).send({ error: 'Advertiser not found' })
      }
      throw err
    }
  })
}
