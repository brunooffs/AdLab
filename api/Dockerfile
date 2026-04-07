# ── Use Debian-based image — has OpenSSL built in (fixes Prisma error) ──────
FROM node:20-bookworm-slim

# Install OpenSSL explicitly — required by Prisma schema engine
RUN apt-get update && apt-get install -y openssl && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy deps first for better Docker layer caching
COPY package*.json ./
COPY prisma ./prisma/

RUN npm install
RUN npx prisma generate

COPY . .

EXPOSE 3000
CMD ["npm", "run", "dev"]
