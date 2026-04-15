import { FastifyInstance } from 'fastify'
import { z } from 'zod'

const createSchema = z.object({
  name:         z.string().min(1),
  advertiserId: z.string(),
  budget:       z.number().positive().default(0),
  status:       z.enum(['ACTIVE', 'PAUSED', 'COMPLETED']).default('ACTIVE'),
  startDate:    z.string().datetime().optional(),
  endDate:      z.string().datetime().optional(),
})

const updateSchema = createSchema.partial()

export async function campaignsRoutes(app: FastifyInstance) {

  // GET /v1/campaigns
  app.get('/', {
    schema: { tags: ['campaigns'], summary: 'List all campaigns' }
  }, async () => {
    return app.prisma.campaign.findMany({
      include: { advertiser: true },
      orderBy: { createdAt: 'desc' },
    })
  })

  // GET /v1/campaigns/:id
  app.get('/:id', {
    schema: { tags: ['campaigns'], summary: 'Get campaign by ID' }
  }, async (req, reply) => {
    const { id } = req.params as { id: string }
    const campaign = await app.prisma.campaign.findUnique({
      where: { id },
      include: { advertiser: true },
    })
    if (!campaign) return reply.status(404).send({ error: 'Not found' })
    return campaign
  })

  // POST /v1/campaigns
  app.post('/', {
    schema: {
      tags: ['campaigns'],
      summary: 'Create campaign',
      body: {
        type: 'object',
        required: ['name', 'advertiserId'],
        properties: {
          name:         { type: 'string' },
          advertiserId: { type: 'string' },
          budget:       { type: 'number' },
          status:       { type: 'string', enum: ['ACTIVE', 'PAUSED', 'COMPLETED'] },
          startDate:    { type: 'string' },
          endDate:      { type: 'string' },
        }
      }
    }
  }, async (req, reply) => {
    const body = createSchema.parse(req.body)
    try {
      const campaign = await app.prisma.campaign.create({
        data: {
          name:         body.name,
          advertiserId: body.advertiserId,
          budget:       body.budget,
          status:       body.status,
          startDate:    body.startDate ? new Date(body.startDate) : new Date(),
          endDate:      body.endDate   ? new Date(body.endDate)   : null,
        },
      })
      return reply.status(201).send(campaign)
    } catch (err: any) {
      if (err.code === 'P2003') {
        return reply.status(404).send({ error: 'Advertiser not found' })
      }
      throw err
    }
  })

  // PATCH /v1/campaigns/:id
  app.patch('/:id', {
    schema: { tags: ['campaigns'], summary: 'Update campaign' }
  }, async (req, reply) => {
    const { id } = req.params as { id: string }
    const body = updateSchema.parse(req.body)
    try {
      const campaign = await app.prisma.campaign.update({
        where: { id },
        data: {
          ...(body.name         !== undefined && { name:         body.name }),
          ...(body.budget       !== undefined && { budget:       body.budget }),
          ...(body.status       !== undefined && { status:       body.status }),
          ...(body.startDate    !== undefined && { startDate:    new Date(body.startDate) }),
          ...(body.endDate      !== undefined && { endDate:      new Date(body.endDate) }),
        },
      })
      return campaign
    } catch (err: any) {
      if (err.code === 'P2025') {
        return reply.status(404).send({ error: 'Not found' })
      }
      throw err
    }
  })

  // DELETE /v1/campaigns/:id
  app.delete('/:id', {
    schema: { tags: ['campaigns'], summary: 'Delete campaign' }
  }, async (req, reply) => {
    const { id } = req.params as { id: string }
    try {
      await app.prisma.campaign.delete({ where: { id } })
      return reply.status(204).send()
    } catch (err: any) {
      if (err.code === 'P2025') {
        return reply.status(404).send({ error: 'Not found' })
      }
      throw err
    }
  })
}
