# pinned 2026-07-26
FROM nginx:1.31-alpine@sha256:db35bfc6b2951e7f8a72db5db120288c127ffaeeb4a6d4b95a26fead017d5913

RUN apk add --no-cache inotify-tools \
    || (sleep 10 && apk add --no-cache inotify-tools) \
    || (sleep 20 && apk add --no-cache inotify-tools)

# Entrypoint mounted as read-only volume from system_data/nginx/entrypoint.sh
