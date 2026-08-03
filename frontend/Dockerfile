# pinned 2026-07-26
FROM node:26-alpine@sha256:233761595746769ebfdb6090f44fc7cdf818ae0ce62d2b37e0367723b9823e36 AS builder

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
FROM node:26-slim@sha256:deae974a69e140f44f434ab29cb519fb5f8fe250fd364b8ca446bd0761acdc6a AS dev

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends wget && rm -rf /var/lib/apt/lists/* \
    || (sleep 10 && apt-get update && apt-get install -y --no-install-recommends wget && rm -rf /var/lib/apt/lists/*) \
    || (sleep 20 && apt-get update && apt-get install -y --no-install-recommends wget && rm -rf /var/lib/apt/lists/*)

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --ignore-scripts

EXPOSE 5173
CMD ["sh", "-c", "if [ ! -f src/api/types.gen.d.ts ] && [ -f /openapi.json ]; then npx --no-install openapi-typescript /openapi.json -o src/api/types.gen.d.ts; fi; exec npm run dev -- --host 0.0.0.0 --port 5173"]

# pinned 2026-07-26
FROM nginx:1.31-alpine@sha256:4a73073bd557c65b759505da037898b61f1be6cbcc3c2c3aeac22d2a470c1752 AS production

COPY --from=builder /app/dist /usr/share/nginx/html

COPY frontend/nginx.spa.conf /etc/nginx/conf.d/default.conf

RUN sed -i '/^user /d' /etc/nginx/nginx.conf \
    && chown -R nginx:nginx /usr/share/nginx/html /var/cache/nginx /var/log/nginx \
    && touch /var/run/nginx.pid && chown nginx:nginx /var/run/nginx.pid

USER nginx

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
