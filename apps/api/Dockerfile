FROM node:22-alpine AS base
ENV PNPM_HOME="/pnpm"
ENV PATH="$PNPM_HOME:$PATH"
RUN corepack enable

# 1. Install Dependencies (Cached Layer)
FROM base AS deps
WORKDIR /app
# Copy root workspace configs
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
# Copy app package config
COPY apps/api/package.json ./apps/api/
COPY packages/contracts/package.json ./packages/contracts/
# Install dependencies (filtering only for this app)
RUN pnpm install --frozen-lockfile --filter api...

# 2. Build Stage
FROM base AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY --from=deps /app/apps/api/node_modules ./apps/api/node_modules
COPY . .
# Build the API
RUN pnpm --filter api build

# 3. Production Runner (Distroless-style minimal)
FROM node:22-alpine AS runner
WORKDIR /app/apps/api
ENV NODE_ENV=production

# Create non-root user (security requirement)
USER node

# Copy built artifacts and app-local node_modules (pnpm workspace layout)
COPY --from=builder --chown=node:node /app/apps/api/dist ./dist
COPY --from=builder --chown=node:node /app/apps/api/node_modules ./node_modules
COPY --from=builder --chown=node:node /app/node_modules/.pnpm /app/node_modules/.pnpm
COPY --from=builder --chown=node:node /app/apps/api/package.json ./package.json

EXPOSE 3000
CMD ["node", "dist/index.js"]
