# ─────────────────────────────────────────────────
# Stage 1 — Dependências
# ─────────────────────────────────────────────────
FROM node:20-alpine AS deps
RUN apk add --no-cache libc6-compat

WORKDIR /app/frontend

COPY package.json package-lock.json ./
RUN npm ci --prefer-offline

# ─────────────────────────────────────────────────
# Stage 2 — Build de produção
# ─────────────────────────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /app/frontend

COPY --from=deps /app/frontend/node_modules ./node_modules
COPY . .

# Garante que o diretório de logs exista para build sem erros
RUN mkdir -p /app/logs

ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

# ─────────────────────────────────────────────────
# Stage 3 — Runtime mínimo
# ─────────────────────────────────────────────────
FROM node:20-alpine AS runner

WORKDIR /app/frontend

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
ENV PORT=3000
ENV HOSTNAME=0.0.0.0

RUN addgroup --system --gid 1001 nodejs \
 && adduser  --system --uid 1001 nextjs

# Cria diretório de logs e ajusta permissões
RUN mkdir -p /app/logs && chown nextjs:nodejs /app/logs

# Copia arquivos públicos e estáticos
COPY --from=builder /app/frontend/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/frontend/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/frontend/.next/static ./.next/static

USER nextjs

EXPOSE 3000

CMD ["node", "server.js"]
