import { FastifyInstance } from 'fastify'
import { z } from 'zod'
import { AdvertiserCommandHandler } from '../handlers/advertiser.command.handler'
import { AdvertiserQueryHandler }   from '../queries/advertiser.queries'
import { AdvertiserReadProjector }  from '../handlers/advertiser.read.projector'

const createSchema = z.object({
  name:  z.string().min(1).max(100),
  email: z.string().email(),
  tier:  z.enum(['STANDARD', 'PREMIUM']).default('STANDARD'),
})

const updateSchema = z.object({
  name:  z.string().min(1).max(100).optional(),
  email: z.string().email().optional(),
  tier:  z.enum(['STANDARD', 'PREMIUM']).optional(),
})

export async function advertisersCqrsRoutes(app: FastifyInstance) {
  const commandHandler = new AdvertiserCommandHandler(app.prisma)
  const queryHandler   = new AdvertiserQueryHandler(app.es)
  new AdvertiserReadProjector(app.es)

  // ── QUERIES ───────────────────────────────────────────────────────────────

  app.get('/', {
    schema: {
      tags: ['advertisers-cqrs'],
      summary: '[CQRS Query] List advertisers from Elasticsearch',
      querystring: {
        type: 'object',
        properties: {
          search: { type: 'string' },
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

  app.get('/search', {
    schema: {
      tags: ['advertisers-cqrs'],
      summary: '[CQRS Query] Full-text search',
      querystring: {
        type: 'object',
        required: ['q'],
        properties: { q: { type: 'string' } }
      }
    }
  }, async (req) => {
    const { q } = req.query as { q: string }
    return queryHandler.search(q)
  })

  app.get('/stats', {
    schema: { tags: ['advertisers-cqrs'], summary: '[CQRS Query] Aggregation stats' }
  }, async () => {
    return queryHandler.countByTier()
  })

  app.get('/:id', {
    schema: { tags: ['advertisers-cqrs'], summary: '[CQRS Query] Get by ID from ES' }
  }, async (req, reply) => {
    const { id } = req.params as { id: string }
    const advertiser = await queryHandler.findById(id)
    if (!advertiser) return reply.status(404).send({ error: 'Not found' })
    return advertiser
  })

  // ── COMMANDS ──────────────────────────────────────────────────────────────

  app.post('/', {
    schema: {
      tags: ['advertisers-cqrs'],
      summary: '[CQRS Command] Create → Postgres + ES projection',
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
        payload: {
          name:  body.name,
          email: body.email,
          tier:  body.tier,
        },
      })
      return reply.status(201).send(result)
    } catch (err: any) {
      if (err.code === 'P2002') {
        return reply.status(409).send({ error: 'Email already exists' })
      }
      throw err
    }
  })

  app.patch('/:id', {
    schema: { tags: ['advertisers-cqrs'], summary: '[CQRS Command] Update → Postgres + ES' }
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

  app.delete('/:id', {
    schema: { tags: ['advertisers-cqrs'], summary: '[CQRS Command] Delete → Postgres + ES' }
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
