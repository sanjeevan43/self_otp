# Multi-stage production build for Node.js 22 TypeScript
FROM node:22-alpine AS builder

WORKDIR /app

# Copy package manifests and configurations
COPY package*.json ./
COPY tsconfig.json ./
COPY prisma ./prisma/

# Install all dependencies (including devDependencies for compilation)
RUN npm ci

# Generate Prisma Client
RUN npx prisma generate

# Copy source code and build
COPY src ./src
COPY tests ./tests

# Build TypeScript
RUN npm run build

# Prune devDependencies for production runtime
RUN npm prune --production

# ----------------------------------------------------
# Production Runner
# ----------------------------------------------------
FROM node:22-alpine AS runner

WORKDIR /app

ENV NODE_ENV=production

# Copy node_modules, compiled dist, and prisma schemas
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/dist ./dist
COPY --from=builder /app/prisma ./prisma
COPY --from=builder /app/package*.json ./

EXPOSE 8000

# Default entrypoint starts the API; worker service overrides CMD
CMD ["node", "dist/src/server.js"]
