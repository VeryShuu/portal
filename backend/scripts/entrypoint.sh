#!/bin/sh
set -e

# Recursive chown of /data is expensive on every restart (large photo trees,
# KB attachments, NC mirror metadata). It only matters once, after the volume
# is first mounted with host-owned UIDs. After that, all writes happen as the
# `portal` user anyway, so ownership stays correct.
#
# We mark the volume with a sentinel file once chown has succeeded; subsequent
# starts skip the recursive walk entirely. To force a re-chown (e.g. after a
# manual operation that left files owned by root), delete /data/.chowned and
# restart the container.
SENTINEL=/data/.chowned
if [ ! -f "$SENTINEL" ]; then
    chown -R portal:portal /data 2>/dev/null || true
    # Use the portal user so the sentinel itself is not root-owned.
    su -s /bin/sh -c "touch '$SENTINEL'" portal 2>/dev/null \
        || touch "$SENTINEL" 2>/dev/null \
        || true
fi

exec gosu portal "$@"
