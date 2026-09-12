#!/bin/sh
# =============================================================================
# render-prometheus.sh — раскрывает ${VAR} в prometheus.tmpl → готовый конфиг.
#
# Зачем: Prometheus (как и Alertmanager) НЕ умеет читать env-переменные в YAML,
# а Docker Compose интерполирует ${VAR} только в своих own .yml, не в
# смонтированных файлах. Раньше токен в prometheus.yml записывался как
# `credentials: ${PORTAL_METRICS_TOKEN}` и оставался ЛИТЕРАЛЬНОЙ строкой —
# при заданном токене scrape падал в 403 (латентный баг, найден при обновлении
# стека до Prometheus 3).
#
# Дополнительно: при ПУСТОМ PORTAL_METRICS_TOKEN блок authorization вырезается
# целиком (маркеры #@auth-begin/#@auth-end в шаблоне) — открытому /metrics
# пустой Bearer-заголовок не нужен.
#
# После рендера конфиг проверяется `promtool check config` (fail-fast на битый
# рендер), затем exec'ается настоящий /bin/prometheus с готовым конфигом.
# Ср. render-alertmanager.sh — тот же паттерн для Alertmanager.
# =============================================================================
set -eu

TMPL="${PROMETHEUS_TMPL:-/etc/prometheus/prometheus.tmpl}"
OUT="${PROMETHEUS_OUT:-/tmp/prometheus.yml}"

# Заменяем ${VAR} на значения из ENVIRON (одна пара внешних кавычек срезается —
# Docker Compose не снимает кавычки из .env). Блок между #@auth-begin/#@auth-end
# вырезается, если PORTAL_METRICS_TOKEN пуст (маркеры в итоговый конфиг не
# попадают никогда). awk вместо sed — переживает спецсимволы в значениях.
awk '
function strip_quotes(v,    first, last, n) {
    n = length(v)
    if (n < 2) return v
    first = substr(v, 1, 1)
    last = substr(v, n, 1)
    if (first == sprintf("%c", 042) && last == sprintf("%c", 042)) return substr(v, 2, n - 2)
    if (first == sprintf("%c", 047) && last == sprintf("%c", 047)) return substr(v, 2, n - 2)
    return v
}
BEGIN {
    drop = (ENVIRON["PORTAL_METRICS_TOKEN"] == "") ? 1 : 0
    skipping = 0
}
/^[[:space:]]*#@auth-begin[[:space:]]*$/ { if (drop) skipping = 1; next }
/^[[:space:]]*#@auth-end[[:space:]]*$/   { skipping = 0; next }
skipping { next }
{
    line = $0
    while (match(line, /\$\{[A-Z_0-9]+\}/)) {
        var = substr(line, RSTART + 2, RLENGTH - 3)
        val = strip_quotes(ENVIRON[var])
        before = substr(line, 1, RSTART - 1)
        after = substr(line, RSTART + RLENGTH)
        line = before val after
    }
    print line
}
' "$TMPL" > "$OUT"

# Sanity: рендер обязан оставить scrape_configs (пустой/битый файл = сломан шаблон).
if ! grep -q '^scrape_configs:' "$OUT"; then
    echo "ERROR: rendered prometheus.yml has no 'scrape_configs:' — template broken?" >&2
    echo "--- rendered content (first 20 lines) ---" >&2
    head -20 "$OUT" >&2
    exit 1
fi

# Fail-fast: невалидный рендер останавливает контейнер здесь, с внятной
# ошибкой promtool, а не внутри prometheus невнятным crash-loop'ом.
if ! /bin/promtool check config "$OUT" >/dev/null 2>&1; then
    echo "ERROR: rendered prometheus.yml failed 'promtool check config':" >&2
    /bin/promtool check config "$OUT" >&2 || true
    exit 1
fi

echo "prometheus config rendered: $OUT ($(wc -l < "$OUT") lines, token=$(if [ -n "${PORTAL_METRICS_TOKEN:-}" ]; then echo set; else echo none; fi))"

# ---------------------------------------------------------------------------
# file_sd-цели для blackbox-проб — из env (формат "name=url,name=url"):
#   BLACKBOX_TARGETS          — модуль http_2xx (TLS проверяется)
#   BLACKBOX_TARGETS_INSECURE — модуль http_2xx_insecure (self-signed/dev)
# Пишем JSON-группы; при пустых env — "[]" (job без целей, алерты молчат).
# file_sd перечитывает файл по refresh_interval — цели можно менять рендером
# без пересборки конфига.
# ---------------------------------------------------------------------------
BLACKBOX_SD="${BLACKBOX_TARGETS_OUT:-/tmp/blackbox-targets.json}"
awk -v tlist="${BLACKBOX_TARGETS:-}" -v ilist="${BLACKBOX_TARGETS_INSECURE:-}" '
function emit(list, module,    n, i, pair, sep, name, url) {
    if (list == "") return
    n = split(list, pairs, ",")
    for (i = 1; i <= n; i++) {
        pair = pairs[i]
        sep = index(pair, "=")
        if (sep < 2) continue
        name = substr(pair, 1, sep - 1)
        url = substr(pair, sep + 1)
        if (url == "") continue
        # В URL кавычек/бэкслэшей не бывает; защита от случайного мусора —
        # иначе JSON молча сломается и file_sd перестанет видеть цели.
        gsub(/[\"\\]/, "", name)
        gsub(/[\"\\]/, "", url)
        printf "%s{\"targets\":[\"%s\"],\"labels\":{\"target_name\":\"%s\",\"module\":\"%s\"}}", (out ? "," : ""), url, name, module
        out = 1
    }
}
BEGIN {
    printf "["
    emit(tlist, "http_2xx")
    emit(ilist, "http_2xx_insecure")
    print "]"
}
' > "$BLACKBOX_SD"
echo "blackbox targets: $BLACKBOX_SD ($(wc -c < "$BLACKBOX_SD") bytes)"

# Передаём управление настоящему prometheus с готовым конфигом.
# Прочие флаги приходят через "$@" из compose command.
exec /bin/prometheus --config.file="$OUT" "$@"
