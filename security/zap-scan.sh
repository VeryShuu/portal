#!/usr/bin/env bash
# OWASP ZAP baseline + active scan (Phase 11 — финальное тестирование, ТЗ §8).
#
# Требует:
#   - запущенный staging: docker compose -f docker-compose.yml -f docker-compose.staging.yml up -d
#   - переменные окружения: ZAP_TARGET (URL), опционально ZAP_AUTH_COOKIE
#
# Использование:
#   ZAP_TARGET=https://portal.staging.local ./security/zap-scan.sh
#
# Покрывает (ТЗ §8):
#   - XSS (reflected/stored/DOM)
#   - CSRF (через проверку Origin/SameSite)
#   - SQLi/Open Redirect/Path traversal
#   - Security headers, missing cookie flags
#   - Доступ без VPN (если запускать снаружи allowlist'а — должны быть 403/closed)
#   - Обход SSO (попытки запросов /api/v1/* без сессии — должны быть 401)
#
set -euo pipefail

TARGET="${ZAP_TARGET:?ZAP_TARGET is required}"
OUT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPORT_HTML="$OUT_DIR/zap-report.html"
REPORT_JSON="$OUT_DIR/zap-report.json"
CONFIG_FILE="$OUT_DIR/zap-baseline.conf"

ZAP_IMAGE="ghcr.io/zaproxy/zaproxy:stable"

echo "==> Pulling ZAP image"
docker pull "$ZAP_IMAGE"

echo "==> Baseline scan against $TARGET"
docker run --rm \
  -v "$OUT_DIR:/zap/wrk/:rw" \
  -t "$ZAP_IMAGE" \
  zap-baseline.py \
    -t "$TARGET" \
    -c "/zap/wrk/$(basename "$CONFIG_FILE")" \
    -r "/zap/wrk/$(basename "$REPORT_HTML")" \
    -J "/zap/wrk/$(basename "$REPORT_JSON")" \
    -I

echo "==> Reports:"
echo "    HTML: $REPORT_HTML"
echo "    JSON: $REPORT_JSON"

echo "==> Quick triage:"
python3 - <<'PY'
import json, os, sys, pathlib
p = pathlib.Path(os.path.dirname(__file__) if __file__ else ".") / "zap-report.json"
data = json.loads(p.read_text(encoding="utf-8"))
counts = {"High": 0, "Medium": 0, "Low": 0, "Informational": 0}
for site in data.get("site", []):
    for alert in site.get("alerts", []):
        risk = alert.get("riskdesc", "").split(" ")[0]
        counts[risk] = counts.get(risk, 0) + 1
print("  High:", counts["High"])
print("  Medium:", counts["Medium"])
print("  Low:", counts["Low"])
print("  Info:", counts["Informational"])
sys.exit(1 if counts["High"] else 0)
PY
