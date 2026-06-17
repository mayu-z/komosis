FROM node:20-alpine AS builder

RUN corepack enable && corepack prepare pnpm@9 --activate

WORKDIR /app

# Copy workspace root files
COPY package.json pnpm-workspace.yaml tsconfig.base.json ./

# Copy ALL workspace package.json files (pnpm needs them for resolution)
COPY packages/contracts/package.json ./packages/contracts/package.json
COPY packages/contracts/tsconfig.json ./packages/contracts/tsconfig.json
COPY backend/gateway/package.json ./backend/gateway/package.json
COPY backend/worker/package.json ./backend/worker/package.json

# Install all deps first (layer cache)
RUN pnpm install --frozen-lockfile || pnpm install

# Copy source for contracts + worker
COPY packages/contracts/src ./packages/contracts/src
COPY packages/contracts/schemas ./packages/contracts/schemas
COPY backend/worker/tsconfig.json ./backend/worker/tsconfig.json
COPY backend/worker/src ./backend/worker/src

# Build
RUN pnpm --filter @rift/contracts run build && pnpm --filter @rift/worker run build

# ── Runtime stage ───────────────────────────────────────
FROM node:20-alpine AS runtime

WORKDIR /app

COPY --from=builder /app/package.json ./package.json
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/packages/contracts/dist ./packages/contracts/dist
COPY --from=builder /app/packages/contracts/package.json ./packages/contracts/package.json
COPY --from=builder /app/packages/contracts/schemas ./packages/contracts/schemas
COPY --from=builder /app/backend/worker/dist ./backend/worker/dist
COPY --from=builder /app/backend/worker/package.json ./backend/worker/package.json
COPY --from=builder /app/backend/worker/node_modules ./backend/worker/node_modules

ENV OUTPUTS_DIR=/app/outputs

RUN mkdir -p /app/outputs

CMD ["node", "backend/worker/dist/index.js"]
