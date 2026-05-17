FROM nginx:1.27-alpine

RUN apk add --no-cache inotify-tools \
    || (sleep 10 && apk add --no-cache inotify-tools) \
    || (sleep 20 && apk add --no-cache inotify-tools)

# Entrypoint mounted as read-only volume from system_data/nginx/entrypoint.sh
