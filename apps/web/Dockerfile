FROM node:22-alpine AS base
ENV PNPM_HOME="/pnpm"
ENV PATH="$PNPM_HOME:$PATH"
ENV ASTRO_TELEMETRY_DISABLED=1
RUN corepack enable

# 1. Install Dependencies
FROM base AS deps
WORKDIR /app
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/web/package.json ./apps/web/
COPY packages/schema/package.json ./packages/schema/
RUN pnpm install --frozen-lockfile --filter web...

# 2. Build Stage
FROM base AS builder
WORKDIR /app
RUN apk add --no-cache git
COPY --from=deps /app/node_modules ./node_modules
COPY --from=deps /app/apps/web/node_modules ./apps/web/node_modules
COPY --from=deps /app/packages/schema/node_modules ./packages/schema/node_modules
COPY . .
# Build Astro SSR (Output: /apps/web/dist)
RUN pnpm --filter web build
RUN node ./apps/web/scripts/generate-git-meta.mjs

# 3. Node Server Runtime
FROM base AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV HOST=0.0.0.0
ENV PORT=8080

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/web/package.json ./apps/web/
COPY packages/schema/package.json ./packages/schema/
COPY packages/schema ./packages/schema

# Install only production deps for the web workspace (and its workspace deps).
RUN pnpm install --frozen-lockfile --prod --filter web...

COPY --from=builder /app/apps/web/dist ./apps/web/dist

EXPOSE 8080
CMD ["node", "./apps/web/dist/server/entry.mjs"]
