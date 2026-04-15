# ─────────────────────────────────────────────────────────────────────────────
#  Dockerfile — AdLab API
#  Multi-stage build — builder compiles, runtime runs
#  Supports linux/arm64 (M1) and linux/amd64 (servers)
# ─────────────────────────────────────────────────────────────────────────────

# ── Stage 1: Builder ──────────────────────────────────────────────────────────
FROM --platform=$BUILDPLATFORM node:20-bookworm-slim AS builder

RUN apt-get update && \
    apt-get install -y openssl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy package files first for better layer caching
COPY package*.json ./
COPY prisma ./prisma/

# Install ALL dependencies (including devDeps for tsx/tsc)
# npm ci ensures reproducible install from lock file
RUN npm ci

# Generate Prisma client for the target platform
RUN npx prisma generate

# Copy source code
COPY . .

# ── Stage 2: Runtime ─────────────────────────────────────────────────────────
FROM node:20-bookworm-slim AS runtime

RUN apt-get update && \
    apt-get install -y openssl curl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy everything from builder
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/prisma       ./prisma
COPY --from=builder /app/package*.json ./
COPY --from=builder /app/src          ./src

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD curl -sf http://localhost:3000/health || exit 1

CMD ["npm", "run", "dev"]
