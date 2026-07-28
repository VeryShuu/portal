# pinned 2026-07-26
FROM nginx:1.31-alpine@sha256:4a73073bd557c65b759505da037898b61f1be6cbcc3c2c3aeac22d2a470c1752

RUN apk add --no-cache inotify-tools \
    || (sleep 10 && apk add --no-cache inotify-tools) \
    || (sleep 20 && apk add --no-cache inotify-tools)

# Entrypoint mounted as read-only volume from system_data/nginx/entrypoint.sh
