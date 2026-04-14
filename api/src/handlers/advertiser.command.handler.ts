// ─────────────────────────────────────────────────────────────────────────────
//  advertiser.command.handler.ts — Write side (Command Handler)
//
//  Receives a command → validates → writes to PostgreSQL (source of truth)
//  → publishes a domain event → event handler syncs Elasticsearch read model
//
//  This is the CQRS write stack:
//    HTTP POST/PATCH/DELETE
//      → Route validates input with Zod
//      → CommandHandler writes to Postgres
//      → DomainEvent published
//      → ReadModelProjector updates ES
// ─────────────────────────────────────────────────────────────────────────────

import { PrismaClient } from '@prisma/client'
import {
  AdvertiserCommand,
  CreateAdvertiserCommand,
  UpdateAdvertiserCommand,
  DeleteAdvertiserCommand,
} from '../commands/advertiser.commands'
import {
  AdvertiserEvent,
  eventBus,
} from '../events/advertiser.events'

export class AdvertiserCommandHandler {
  constructor(private readonly prisma: PrismaClient) {}

  async handle(command: AdvertiserCommand): Promise<{ id: string }> {
    switch (command.type) {
      case 'CREATE_ADVERTISER':
        return this.handleCreate(command)
      case 'UPDATE_ADVERTISER':
        return this.handleUpdate(command)
      case 'DELETE_ADVERTISER':
        return this.handleDelete(command)
      default:
        throw new Error(`Unknown command type`)
    }
  }

  // ── Create ────────────────────────────────────────────────────────────────
  private async handleCreate(cmd: CreateAdvertiserCommand) {
    const advertiser = await this.prisma.advertiser.create({
      data: {
        name:  cmd.payload.name,
        email: cmd.payload.email,
        tier:  cmd.payload.tier,
      },
    })

    // Publish event — read model projector will sync to ES
    await eventBus.publish({
      type:       'ADVERTISER_CREATED',
      occurredAt: new Date().toISOString(),
      payload: {
        id:        advertiser.id,
        name:      advertiser.name,
        email:     advertiser.email,
        tier:      advertiser.tier,
        createdAt: advertiser.createdAt.toISOString(),
      },
    })

    return { id: advertiser.id }
  }

  // ── Update ────────────────────────────────────────────────────────────────
  private async handleUpdate(cmd: UpdateAdvertiserCommand) {
    const advertiser = await this.prisma.advertiser.update({
      where: { id: cmd.payload.id },
      data: {
        ...(cmd.payload.name  && { name:  cmd.payload.name }),
        ...(cmd.payload.email && { email: cmd.payload.email }),
        ...(cmd.payload.tier  && { tier:  cmd.payload.tier }),
      },
    })

    await eventBus.publish({
      type:       'ADVERTISER_UPDATED',
      occurredAt: new Date().toISOString(),
      payload: {
        id:        advertiser.id,
        name:      advertiser.name,
        email:     advertiser.email,
        tier:      advertiser.tier,
        updatedAt: advertiser.updatedAt.toISOString(),
      },
    })

    return { id: advertiser.id }
  }

  // ── Delete ────────────────────────────────────────────────────────────────
  private async handleDelete(cmd: DeleteAdvertiserCommand) {
    await this.prisma.advertiser.delete({
      where: { id: cmd.payload.id },
    })

    await eventBus.publish({
      type:       'ADVERTISER_DELETED',
      occurredAt: new Date().toISOString(),
      payload:    { id: cmd.payload.id },
    })

    return { id: cmd.payload.id }
  }
}
