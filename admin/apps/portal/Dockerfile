# syntax=docker/dockerfile:1

# ── build stage ───────────────────────────────────────────────────────────────
FROM node:22-slim AS build
RUN corepack enable && corepack prepare pnpm@9.12.0 --activate
WORKDIR /admin

ARG NEXT_PUBLIC_API_BASE_URL
ENV NEXT_PUBLIC_API_BASE_URL=$NEXT_PUBLIC_API_BASE_URL \
    NEXT_TELEMETRY_DISABLED=1 \
    NODE_ENV=production

COPY . .
# NODE_ENV=production (set above, needed so `next build` emits the prod CSP)
# makes pnpm skip devDependencies — but the build toolchain (tailwindcss,
# @tailwindcss/postcss, @sacco/tsconfig, typescript) lives there. Force a full
# install so the build has them; runtime uses the standalone bundle, not these.
RUN pnpm install --frozen-lockfile --prod=false
# Next standalone expects a public dir; create it if the app has none.
RUN mkdir -p apps/portal/public && pnpm --filter @sacco/portal build

# ── runtime stage ─────────────────────────────────────────────────────────────
FROM node:22-slim AS runner
WORKDIR /admin
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0

RUN groupadd --gid 1001 nodejs && \
    useradd --uid 1001 --gid nodejs --no-create-home --shell /bin/false nextjs

# Standalone output: server + traced node_modules, static assets, public.
COPY --from=build --chown=nextjs:nodejs /admin/apps/portal/.next/standalone ./
COPY --from=build --chown=nextjs:nodejs /admin/apps/portal/.next/static ./apps/portal/.next/static
COPY --from=build --chown=nextjs:nodejs /admin/apps/portal/public ./apps/portal/public

USER nextjs
EXPOSE 3000
CMD ["node", "apps/portal/server.js"]
