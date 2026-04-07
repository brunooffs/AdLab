#!/bin/sh

# Health check
curl http://localhost:3000/health

# Data source connectivity
curl http://localhost:3000/v1/metrics/health

# Create your first advertiser
curl -X POST http://localhost:3000/v1/advertisers \
  -H "Content-Type: application/json" \
  -d '{"name": "Acme Corp", "email": "acme@example.com", "tier": "PREMIUM"}'

# List advertisers
curl http://localhost:3000/v1/advertisers

# Create a campaign (use the id returned from the advertiser above)
curl -X POST http://localhost:3000/v1/campaigns \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Summer 2026",
    "advertiserId": "PASTE_ID_HERE",
    "budget": 50000,
    "startDate": "2026-06-01T00:00:00Z",
    "status": "ACTIVE"
  }'

# GraphQL — query advertisers
curl -X POST http://localhost:3000/graphql \
  -H "Content-Type: application/json" \
  -d '{"query": "{ advertisers { id name email tier campaigns { id name status } } }"}'

# Trending ads from Elasticsearch
curl http://localhost:3000/v1/metrics/trending?limit=5