#!/bin/sh
# Invoked only by the root-only, one-shot ``data-permissions-init`` service.
# Long-running application containers use the unprivileged ``portal`` account.
set -eu

PORTAL_UID="${PORTAL_UID:-1001}"
PORTAL_GID="${PORTAL_GID:-1001}"

for path in /data/upload_data /data/settings /data/secrets /data/certs /data/nginx /data/nginx-conf; do
    if [ ! -d "$path" ]; then
        echo "[data-permissions-init] expected bind mount is missing: $path" >&2
        exit 1
    fi
    chown -R "$PORTAL_UID:$PORTAL_GID" "$path"
done

echo "[data-permissions-init] bind-mount ownership prepared for ${PORTAL_UID}:${PORTAL_GID}"
