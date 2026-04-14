// ─────────────────────────────────────────────────────────────────────────────
//  advertiser.read.projector.ts — Read Model Projector
//
//  Listens to domain events and projects them into Elasticsearch.
//  This is what keeps the read model (ES) in sync with the write model (PG).
//
//  Pattern: Event Sourcing projection
//    ADVERTISER_CREATED → upsert doc into ES index
//    ADVERTISER_UPDATED → update doc in ES index
//    ADVERTISER_DELETED → delete doc from ES index
//
//  In production this would be a Kafka consumer running as a separate
//  microservice. Here it runs in-process for simplicity, but the interface
//  is identical — it just subscribes to events and projects state.
// ─────────────────────────────────────────────────────────────────────────────

import { Client } from '@elastic/elasticsearch'
import {
  AdvertiserCreatedEvent,
  AdvertiserUpdatedEvent,
  AdvertiserDeletedEvent,
  eventBus,
} from '../events/advertiser.events'

const ES_INDEX = 'advertisers'

export class AdvertiserReadProjector {
  constructor(private readonly es: Client) {
    this.registerHandlers()
  }

  private registerHandlers() {
    // Subscribe to all advertiser domain events
    eventBus.subscribe<AdvertiserCreatedEvent>(
      'ADVERTISER_CREATED',
      this.onCreated.bind(this)
    )

    eventBus.subscribe<AdvertiserUpdatedEvent>(
      'ADVERTISER_UPDATED',
      this.onUpdated.bind(this)
    )

    eventBus.subscribe<AdvertiserDeletedEvent>(
      'ADVERTISER_DELETED',
      this.onDeleted.bind(this)
    )

    console.log('[CQRS] AdvertiserReadProjector registered — syncing PG → ES')
  }

  // ── Project CREATED event → ES upsert ────────────────────────────────────
  private async onCreated(event: AdvertiserCreatedEvent) {
    try {
      await this.es.index({
        index: ES_INDEX,
        id:    event.payload.id,
        document: {
          id:         event.payload.id,
          name:       event.payload.name,
          email:      event.payload.email,
          tier:       event.payload.tier,
          createdAt:  event.payload.createdAt,
          indexedAt:  event.occurredAt,
          campaigns:  [],       // populated when campaigns are added
        },
      })
      console.log(`[CQRS] Projected CREATED → ES: ${event.payload.id}`)
    } catch (err) {
      console.error('[CQRS] Failed to project CREATED event:', err)
    }
  }

  // ── Project UPDATED event → ES update ────────────────────────────────────
  private async onUpdated(event: AdvertiserUpdatedEvent) {
    try {
      await this.es.update({
        index: ES_INDEX,
        id:    event.payload.id,
        doc: {
          ...(event.payload.name  && { name:  event.payload.name }),
          ...(event.payload.email && { email: event.payload.email }),
          ...(event.payload.tier  && { tier:  event.payload.tier }),
          updatedAt: event.payload.updatedAt,
          indexedAt: event.occurredAt,
        },
        doc_as_upsert: true,
      })
      console.log(`[CQRS] Projected UPDATED → ES: ${event.payload.id}`)
    } catch (err) {
      console.error('[CQRS] Failed to project UPDATED event:', err)
    }
  }

  // ── Project DELETED event → ES delete ────────────────────────────────────
  private async onDeleted(event: AdvertiserDeletedEvent) {
    try {
      await this.es.delete({
        index: ES_INDEX,
        id:    event.payload.id,
      }).catch(() => {
        // Ignore 404 — doc may not exist in ES
      })
      console.log(`[CQRS] Projected DELETED → ES: ${event.payload.id}`)
    } catch (err) {
      console.error('[CQRS] Failed to project DELETED event:', err)
    }
  }
}
