"""Export FastAPI OpenAPI schema to /tmp/openapi.json (or path from argv)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from app.main import app

target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/openapi.json")
target.write_text(
    json.dumps(app.openapi(), indent=2, ensure_ascii=False),
    encoding="utf-8",
)
print(f"OpenAPI schema written to {target} ({target.stat().st_size} bytes)")
