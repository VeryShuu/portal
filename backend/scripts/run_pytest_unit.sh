#!/bin/sh
set -e
cd /app
exec python -m pytest tests/unit -x -q --no-header -p no:cacheprovider --no-cov "$@"
