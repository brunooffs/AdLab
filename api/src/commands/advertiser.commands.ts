// ─────────────────────────────────────────────────────────────────────────────
//  advertiser.commands.ts — Command definitions (write side)
//
//  Commands represent INTENT to change state.
//  They are validated, then handled by a CommandHandler.
//  On success they emit a DomainEvent to sync the read model.
// ─────────────────────────────────────────────────────────────────────────────

export type AdvertiserTier = 'STANDARD' | 'PREMIUM'

// ── Create ────────────────────────────────────────────────────────────────────
export interface CreateAdvertiserCommand {
  type: 'CREATE_ADVERTISER'
  payload: {
    name:  string
    email: string
    tier:  AdvertiserTier
  }
}

// ── Update ────────────────────────────────────────────────────────────────────
export interface UpdateAdvertiserCommand {
  type: 'UPDATE_ADVERTISER'
  payload: {
    id:     string
    name?:  string
    email?: string
    tier?:  AdvertiserTier
  }
}

// ── Delete ────────────────────────────────────────────────────────────────────
export interface DeleteAdvertiserCommand {
  type: 'DELETE_ADVERTISER'
  payload: {
    id: string
  }
}

// ── Union type ────────────────────────────────────────────────────────────────
export type AdvertiserCommand =
  | CreateAdvertiserCommand
  | UpdateAdvertiserCommand
  | DeleteAdvertiserCommand
