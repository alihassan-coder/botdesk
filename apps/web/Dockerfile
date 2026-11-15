# syntax=docker/dockerfile:1
#
# The BotDesk web app image: a Next.js standalone server on port 3000.
#
# Build from the REPO ROOT (pnpm workspace):
#   docker build -f apps/web/Dockerfile --build-arg NEXT_PUBLIC_API_URL=https://botdesk.example.com -t botdesk-web .
# Normally deploy/docker-compose.yml builds it for you.
#
# NEXT_PUBLIC_API_URL is baked into the browser code AT BUILD TIME (Next inlines NEXT_PUBLIC_*).
# Changing it means rebuilding this image; setting it only when the container starts does nothing.
# Left empty, the web app runs on its built-in demo data and never calls the API.

ARG NODE_VERSION=22

FROM node:${NODE_VERSION}-bookworm-slim AS base
ENV COREPACK_ENABLE_DOWNLOAD_PROMPT=0 \
    NEXT_TELEMETRY_DISABLED=1
# corepack installs the pnpm version named in package.json ("packageManager"). The corepack that
# ships with Node can be too old to verify new pnpm releases, so update it first.
RUN npm install --global corepack@latest && corepack enable

# ---- build: install the web app's packages and run `next build` ----
FROM base AS build
WORKDIR /repo

# Every workspace manifest, so `--frozen-lockfile` sees the same workspace the lockfile describes.
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/web/package.json apps/web/
COPY apps/api/package.json apps/api/
COPY packages/plugin-sdk/package.json packages/plugin-sdk/
COPY plugins/demo/package.json plugins/demo/
RUN pnpm install --frozen-lockfile --filter "@botdesk/web..."

COPY apps/web apps/web

ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL} \
    BOTDESK_STANDALONE=true
# The standalone server mirrors the monorepo (Next traces from the pnpm-lock.yaml folder), so
# server.js lands in .next/standalone/apps/web/. Fail the build here if that ever changes.
RUN pnpm --filter @botdesk/web build \
 && test -f apps/web/.next/standalone/apps/web/server.js

# ---- runtime: only the standalone server and its static files; non-root ----
FROM node:${NODE_VERSION}-bookworm-slim AS runtime
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0
WORKDIR /app

# The `node` user (uid 1000) comes with the image; it owns the files so Next can write its cache.
COPY --from=build --chown=node:node /repo/apps/web/.next/standalone ./
COPY --from=build --chown=node:node /repo/apps/web/.next/static ./apps/web/.next/static

USER node
EXPOSE 3000

HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
  CMD ["node", "-e", "fetch('http://127.0.0.1:3000/').then(r => process.exit(r.status < 500 ? 0 : 1)).catch(() => process.exit(1))"]

CMD ["node", "apps/web/server.js"]
