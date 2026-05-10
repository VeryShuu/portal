#!/bin/sh
set -e
cd /app
exec env INTEGRATION_DB=true INTEGRATION_REDIS=true \
    python -m pytest tests/ -q --no-header -p no:cacheprovider --no-cov "$@"
