# pinned 2026-07-26
FROM node:26-alpine@sha256:e88a35be04478413b7c71c455cd9865de9b9360e1f43456be5951032d7ac1a66 AS builder

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
FROM node:26-slim@sha256:715e55e4b84e4bb0ff48e49b398a848f08e55daed8eb6a0ea1839ae53bc57583 AS dev

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
