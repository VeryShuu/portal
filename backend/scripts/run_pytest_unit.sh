#!/bin/sh
pip install --quiet --no-warn-script-location pytest pytest-asyncio pytest-cov httpx aiosqlite freezegun fakeredis 2>&1 | tail -5
cd /app
exec python -m pytest tests/unit -x -q --no-header -p no:cacheprovider --no-cov
