# ─────────────────────────────────────────────────────────────────────────────
#  Dockerfile — AdLab API (production build)
#  Uses tsc to compile TypeScript → JavaScript
#  No tsx/esbuild at runtime — avoids platform binary issues
# ─────────────────────────────────────────────────────────────────────────────

FROM node:22-bookworm-slim AS builder

RUN apt-get update && \
    apt-get install -y openssl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY package*.json ./
COPY prisma ./prisma/
COPY tsconfig.json ./

# Install ALL deps including devDeps (needed for tsc)
RUN npm ci

# Generate Prisma client
RUN npx prisma generate

# Copy source and compile TypeScript → JavaScript
COPY src ./src
RUN npx tsc --outDir dist --noEmit false

# ── Runtime ───────────────────────────────────────────────────────────────────
FROM node:22-bookworm-slim AS runtime

RUN apt-get update && \
    apt-get install -y openssl curl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy compiled JS and production deps only
COPY --from=builder /app/dist         ./dist
COPY --from=builder /app/prisma       ./prisma
COPY --from=builder /app/package*.json ./

# Install PRODUCTION deps only — no tsx, no esbuild
RUN npm ci --omit=dev

# Re-generate Prisma client for this platform
RUN npx prisma generate

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD curl -sf http://localhost:3000/health || exit 1

# Run compiled JavaScript directly with node — no tsx needed
CMD ["node", "dist/index.js"]
