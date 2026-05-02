#!/bin/sh
set -e
chown -R portal:portal /data 2>/dev/null || true
exec gosu portal "$@"
