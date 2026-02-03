FROM node:22-alpine AS base
ENV PNPM_HOME="/pnpm"
ENV PATH="$PNPM_HOME:$PATH"
RUN corepack enable

# 1. Install Dependencies
FROM base AS deps
WORKDIR /app
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/web/package.json ./apps/web/
RUN pnpm install --frozen-lockfile --filter web...

# 2. Build Stage
FROM base AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY --from=deps /app/apps/web/node_modules ./apps/web/node_modules
COPY . .
# Build Astro (Output: /apps/web/dist)
RUN pnpm --filter web build

# 3. Nginx Server (non-root)
FROM nginxinc/nginx-unprivileged:alpine AS runner
# Copy static assets to Nginx default directory
COPY --from=builder /app/apps/web/dist /usr/share/nginx/html
# Optional: Add custom nginx.conf if needed for clean URLs
# COPY apps/web/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 8080
CMD ["nginx", "-g", "daemon off;"]
