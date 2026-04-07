import { FastifyInstance } from 'fastify'
import { z } from 'zod'

const createSchema = z.object({
  name:  z.string().min(1).max(100),
  email: z.string().email(),
  tier:  z.enum(['STANDARD', 'PREMIUM']).default('STANDARD')
})

const updateSchema = createSchema.partial()

export async function advertisersRoutes(app: FastifyInstance) {

  // GET /v1/advertisers
  app.get('/', {
    schema: {
      tags: ['advertisers'],
      summary: 'List all advertisers'
      // No response schema — let Fastify serialize the full Prisma object
    }
  }, async () => {
    return app.prisma.advertiser.findMany({
      include: { campaigns: true },
      orderBy: { createdAt: 'desc' }
    })
  })

  // GET /v1/advertisers/:id
  app.get('/:id', {
    schema: {
      tags: ['advertisers'],
      summary: 'Get advertiser by ID',
      params: {
        type: 'object',
        properties: { id: { type: 'string' } }
      }
    }
  }, async (req, reply) => {
    const { id } = req.params as { id: string }
    const advertiser = await app.prisma.advertiser.findUnique({
      where: { id },
      include: { campaigns: true }
    })
    if (!advertiser) return reply.status(404).send({ error: 'Advertiser not found' })
    return advertiser
  })

  // POST /v1/advertisers
  app.post('/', {
    schema: {
      tags: ['advertisers'],
      summary: 'Create a new advertiser',
      body: {
        type: 'object',
        required: ['name', 'email'],
        properties: {
          name:  { type: 'string' },
          email: { type: 'string' },
          tier:  { type: 'string', enum: ['STANDARD', 'PREMIUM'] }
        }
      }
    }
  }, async (req, reply) => {
    const body = createSchema.parse(req.body)
    try {
      const advertiser = await app.prisma.advertiser.create({
        data: body,
        include: { campaigns: true }
      })
      return reply.status(201).send(advertiser)
    } catch (err: any) {
      if (err.code === 'P2002') {
        return reply.status(409).send({
          error: 'Conflict',
          message: 'An advertiser with this email already exists'
        })
      }
      throw err
    }
  })

  // PATCH /v1/advertisers/:id
  app.patch('/:id', {
    schema: {
      tags: ['advertisers'],
      summary: 'Update an advertiser',
      params: {
        type: 'object',
        properties: { id: { type: 'string' } }
      },
      body: {
        type: 'object',
        properties: {
          name:  { type: 'string' },
          email: { type: 'string' },
          tier:  { type: 'string', enum: ['STANDARD', 'PREMIUM'] }
        }
      }
    }
  }, async (req, reply) => {
    const { id } = req.params as { id: string }
    const body = updateSchema.parse(req.body)
    try {
      const advertiser = await app.prisma.advertiser.update({
        where: { id },
        data: body,
        include: { campaigns: true }
      })
      return advertiser
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
      tags: ['advertisers'],
      summary: 'Delete an advertiser',
      params: {
        type: 'object',
        properties: { id: { type: 'string' } }
      }
    }
  }, async (req, reply) => {
    const { id } = req.params as { id: string }
    try {
      await app.prisma.advertiser.delete({ where: { id } })
      return reply.status(204).send()
    } catch (err: any) {
      if (err.code === 'P2025') {
        return reply.status(404).send({ error: 'Advertiser not found' })
      }
      throw err
    }
  })
}
