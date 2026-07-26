FROM nginx:1.27-alpine@sha256:65645c7bb6a0661892a8b03b89d0743208a18dd2f3f17a54ef4b76fb8e2f2a10 # pinned 2026-07-26

RUN apk add --no-cache inotify-tools \
    || (sleep 10 && apk add --no-cache inotify-tools) \
    || (sleep 20 && apk add --no-cache inotify-tools)

# Entrypoint mounted as read-only volume from system_data/nginx/entrypoint.sh
