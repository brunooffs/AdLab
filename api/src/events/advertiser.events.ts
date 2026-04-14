// ─────────────────────────────────────────────────────────────────────────────
//  advertiser.events.ts — Domain Events
//
//  Events represent something that HAS happened (past tense).
//  They are published after a command succeeds and consumed by
//  the read model projector to keep ES in sync with Postgres.
// ─────────────────────────────────────────────────────────────────────────────

export interface AdvertiserCreatedEvent {
  type:      'ADVERTISER_CREATED'
  occurredAt: string           // ISO timestamp
  payload: {
    id:        string
    name:      string
    email:     string
    tier:      string
    createdAt: string
  }
}

export interface AdvertiserUpdatedEvent {
  type:       'ADVERTISER_UPDATED'
  occurredAt: string
  payload: {
    id:        string
    name?:     string
    email?:    string
    tier?:     string
    updatedAt: string
  }
}

export interface AdvertiserDeletedEvent {
  type:       'ADVERTISER_DELETED'
  occurredAt: string
  payload: {
    id: string
  }
}

export type AdvertiserEvent =
  | AdvertiserCreatedEvent
  | AdvertiserUpdatedEvent
  | AdvertiserDeletedEvent


// ── Simple in-process event bus ───────────────────────────────────────────────
// In production this would be Kafka — events published here would flow
// through Kafka → consumer → ES projector. For the lab we keep it in-process
// but the interface is the same: publish → subscribe pattern.

type EventHandler<T> = (event: T) => Promise<void>

class EventBus {
  private handlers = new Map<string, EventHandler<any>[]>()

  subscribe<T>(eventType: string, handler: EventHandler<T>) {
    const existing = this.handlers.get(eventType) || []
    this.handlers.set(eventType, [...existing, handler])
  }

  async publish(event: AdvertiserEvent): Promise<void> {
    const handlers = this.handlers.get(event.type) || []
    await Promise.all(handlers.map(h => h(event)))
  }
}

// Singleton event bus — shared across the application
export const eventBus = new EventBus()
