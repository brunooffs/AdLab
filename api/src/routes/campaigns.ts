import { FastifyInstance } from 'fastify'
import { z } from 'zod'

const createSchema = z.object({
  name:         z.string().min(1),
  advertiserId: z.string(),
  budget:       z.number().positive(),
  startDate:    z.string().datetime(),
  endDate:      z.string().datetime().optional(),
  status:       z.enum(['ACTIVE', 'PAUSED', 'COMPLETED']).default('ACTIVE')
})

export async function campaignsRoutes(app: FastifyInstance) {

  // GET /v1/campaigns
  app.get('/', {
    schema: { tags: ['campaigns'], summary: 'List all campaigns' }
  }, async (req) => {
    const { advertiserId, status } = req.query as any
    return app.prisma.campaign.findMany({
      where: {
        ...(advertiserId ? { advertiserId } : {}),
        ...(status       ? { status }       : {})
      },
      include: { advertiser: true },
      orderBy: { createdAt: 'desc' }
    })
  })

  // POST /v1/campaigns
  app.post('/', {
    schema: {
      tags: ['campaigns'],
      summary: 'Create a new campaign',
      body: {
        type: 'object',
        required: ['name', 'advertiserId', 'budget', 'startDate'],
        properties: {
          name:         { type: 'string' },
          advertiserId: { type: 'string' },
          budget:       { type: 'number' },
          startDate:    { type: 'string' },
          endDate:      { type: 'string' },
          status:       { type: 'string' }
        }
      }
    }
  }, async (req, reply) => {
    const body = createSchema.parse(req.body)
    const campaign = await app.prisma.campaign.create({
      data: {
        ...body,
        startDate: new Date(body.startDate),
        endDate:   body.endDate ? new Date(body.endDate) : undefined
      }
    })
    return reply.status(201).send(campaign)
  })

  // PATCH /v1/campaigns/:id/status
  app.patch('/:id/status', {
    schema: {
      tags: ['campaigns'],
      summary: 'Update campaign status',
      params: { type: 'object', properties: { id: { type: 'string' } } },
      body: {
        type: 'object',
        required: ['status'],
        properties: { status: { type: 'string', enum: ['ACTIVE', 'PAUSED', 'COMPLETED'] } }
      }
    }
  }, async (req, reply) => {
    const { id } = req.params as { id: string }
    const { status } = req.body as { status: any }
    try {
      const campaign = await app.prisma.campaign.update({ where: { id }, data: { status } })
      return campaign
    } catch {
      return reply.status(404).send({ error: 'Campaign not found' })
    }
  })
}
