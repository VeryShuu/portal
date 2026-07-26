FROM node:24-alpine@sha256:a0b9bf06e4e6193cf7a0f58816cc935ff8c2a908f81e6f1a95432d679c54fbfd AS builder # pinned 2026-07-26

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
FROM node:24-slim@sha256:6f7b03f7c2c8e2e784dcf9295400527b9b1270fd37b7e9a7285cf83b6951452d AS dev # pinned 2026-07-26

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends wget && rm -rf /var/lib/apt/lists/* \
    || (sleep 10 && apt-get update && apt-get install -y --no-install-recommends wget && rm -rf /var/lib/apt/lists/*) \
    || (sleep 20 && apt-get update && apt-get install -y --no-install-recommends wget && rm -rf /var/lib/apt/lists/*)

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --ignore-scripts

EXPOSE 5173
CMD ["sh", "-c", "if [ ! -f src/api/types.gen.d.ts ] && [ -f /openapi.json ]; then npx --no-install openapi-typescript /openapi.json -o src/api/types.gen.d.ts; fi; exec npm run dev -- --host 0.0.0.0 --port 5173"]

FROM nginx:1.27-alpine@sha256:65645c7bb6a0661892a8b03b89d0743208a18dd2f3f17a54ef4b76fb8e2f2a10 AS production # pinned 2026-07-26

COPY --from=builder /app/dist /usr/share/nginx/html

COPY frontend/nginx.spa.conf /etc/nginx/conf.d/default.conf

RUN sed -i '/^user /d' /etc/nginx/nginx.conf \
    && chown -R nginx:nginx /usr/share/nginx/html /var/cache/nginx /var/log/nginx \
    && touch /var/run/nginx.pid && chown nginx:nginx /var/run/nginx.pid

USER nginx

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
