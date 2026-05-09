FROM node:24-alpine AS builder

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
FROM node:24-alpine AS dev

WORKDIR /app

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --ignore-scripts

EXPOSE 5173
CMD ["sh", "-c", "if [ ! -f src/api/types.gen.d.ts ] && [ -f /openapi.json ]; then npx --no-install openapi-typescript /openapi.json -o src/api/types.gen.d.ts; fi; exec npm run dev -- --host 0.0.0.0 --port 5173"]

FROM nginx:1.27-alpine AS production

COPY --from=builder /app/dist /usr/share/nginx/html

COPY frontend/nginx.spa.conf /etc/nginx/conf.d/default.conf

RUN sed -i '/^user /d' /etc/nginx/nginx.conf \
    && chown -R nginx:nginx /usr/share/nginx/html /var/cache/nginx /var/log/nginx \
    && touch /var/run/nginx.pid && chown nginx:nginx /var/run/nginx.pid

USER nginx

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
