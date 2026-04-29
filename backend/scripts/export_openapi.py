"""Экспорт OpenAPI-спецификации FastAPI в JSON-файл.

Запуск:
    cd backend && python scripts/export_openapi.py [--output ../openapi.json]

Используется для:
  - публикации спецификации заказчику (поставка, ТЗ §9);
  - generation Postman collection / клиентских SDK;
  - регрессионной проверки в CI (diff против предыдущей версии).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Export FastAPI OpenAPI spec to JSON")
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "openapi.json",
        help="Path to output JSON file (default: ../../openapi.json)",
    )
    parser.add_argument(
        "--indent",
        type=int,
        default=2,
        help="JSON indent (default: 2)",
    )
    args = parser.parse_args()

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from app.main import app  # type: ignore[import-not-found]

    spec = app.openapi()
    args.output.write_text(
        json.dumps(spec, indent=args.indent, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"OpenAPI spec exported: {args.output} ({args.output.stat().st_size} bytes)")
    print(
        f"Endpoints: {len(spec.get('paths', {}))}, schemas: {len(spec.get('components', {}).get('schemas', {}))}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
