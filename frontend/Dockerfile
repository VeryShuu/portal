# pinned 2026-07-26
FROM node:26-alpine@sha256:aadf416b2cdce311a8811ba3f0608a61b77dbf997500e2eafe781b51f6a0b019 AS builder

WORKDIR /app

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --ignore-scripts

COPY openapi.json /openapi.json
COPY frontend/ .
RUN npm run gen:types
RUN npm run build

# ── dev-стадия: Vite dev server с HMR для setup.sh пункта "Разработка" ─────────
# Используется через docker-compose.dev.yml (target: dev). Исходники монтируются
# bind-mount'ом, openapi.json — отдельным volume в /openapi.json.
# pinned 2026-07-26
FROM node:26-slim@sha256:4ebb5ace66f15a24c14c492e01a8beeed4fddf970a856109f5126e703e5fe503 AS dev

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends wget && rm -rf /var/lib/apt/lists/* \
    || (sleep 10 && apt-get update && apt-get install -y --no-install-recommends wget && rm -rf /var/lib/apt/lists/*) \
    || (sleep 20 && apt-get update && apt-get install -y --no-install-recommends wget && rm -rf /var/lib/apt/lists/*)

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --ignore-scripts

EXPOSE 5173
CMD ["sh", "-c", "if [ ! -f src/api/types.gen.d.ts ] && [ -f /openapi.json ]; then npx --no-install openapi-typescript /openapi.json -o src/api/types.gen.d.ts; fi; exec npm run dev -- --host 0.0.0.0 --port 5173"]

# pinned 2026-07-26
FROM nginx:1.31-alpine@sha256:db35bfc6b2951e7f8a72db5db120288c127ffaeeb4a6d4b95a26fead017d5913 AS production

COPY --from=builder /app/dist /usr/share/nginx/html

COPY frontend/nginx.spa.conf /etc/nginx/conf.d/default.conf

RUN sed -i '/^user /d' /etc/nginx/nginx.conf \
    && chown -R nginx:nginx /usr/share/nginx/html /var/cache/nginx /var/log/nginx \
    && touch /var/run/nginx.pid && chown nginx:nginx /var/run/nginx.pid

USER nginx

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
