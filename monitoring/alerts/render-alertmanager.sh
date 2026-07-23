#!/bin/sh
# =============================================================================
# render-alertmanager.sh — раскрывает ${VAR} в alertmanager.tmpl → готовый конфиг.
#
# Зачем: Alertmanager (Go-приложение) НЕ умеет читать env-переменные в YAML.
# Docker Compose интерполирует ${VAR} только в своих own .yml, но НЕ в
# содержимом смонтированных файлов. Образ prom/alertmanager — busybox-only,
# envsubst в нём нет. Поэтому этот скрипт (через awk) раскрывает плейсхолдеры
# ${ALERT_*} значениями из окружения и кладёт финальный конфиг в /tmp.
#
# Вызывается как entrypoint контейнера alertmanager (см. overlay compose).
# Запускается ДО /bin/alertmanager, затем exec'ает его с готовым конфигом.
#
# awk (вместо sed) выбран намеренно: sed ломается на спецсимволах в паролях
# (! @ / и т.п.), которые часто встречаются в SMTP-credentials.
# =============================================================================
set -eu

TMPL="${ALERTMANAGER_TMPL:-/etc/alertmanager/alertmanager.tmpl}"
OUT="${ALERTMANAGER_OUT:-/tmp/alertmanager.yml}"

# Заменяем все ${VAR} на значения из ENVIRON[var]. Несуществующие переменные
# раскрываются в пустую строку (Alertmanager воспринимает пустой SMTP как
# no-op — алерты видны только в UI).
#
# Реализация: для каждой найденной ${VAR} вырезаем её через substr (RSTART,
# RLENGTH покрывают ВЕСЬ токен "${VAR}" включая $ и {}) и склеиваем строку
# до/значение/после. Этот подход надёжнее gsub с регэкспом, т.к. переживает
# любые спецсимволы в значениях (!, @, /, \ в паролях SMTP).
awk '
# Срезаем ОДНУ пару внешних кавычек со значения env. Пользователи часто пишут
# PASSWORD="secret" в .env, а Docker Compose НЕ снимает эти кавычки — они
# становятся частью значения и ломают YAML (двойное квотирование). Используем
# числовые коды (042 = "  047 = '\''  в ASCII), чтобы избежать кавычек в самом
# awk-скрипте (он сам внутри shell-одинарных кавычек).
function strip_quotes(v,    first, last, n) {
    n = length(v)
    if (n < 2) return v
    first = substr(v, 1, 1)
    last = substr(v, n, 1)
    if (first == sprintf("%c", 042) && last == sprintf("%c", 042)) return substr(v, 2, n - 2)
    if (first == sprintf("%c", 047) && last == sprintf("%c", 047)) return substr(v, 2, n - 2)
    return v
}
{
    line = $0
    while (match(line, /\$\{[A-Z_]+\}/)) {
        var = substr(line, RSTART + 2, RLENGTH - 3)
        val = strip_quotes(ENVIRON[var])
        before = substr(line, 1, RSTART - 1)
        after = substr(line, RSTART + RLENGTH)
        line = before val after
    }
    print line
}
' "$TMPL" > "$OUT"

# Проверяем, что конфиг валиден (route обязателен). Если файл пуст/битый —
# alertmanager упадёт с понятной ошибкой, но мы хотим явный фейл здесь.
if ! grep -q '^route:' "$OUT"; then
    echo "ERROR: rendered alertmanager.yml has no 'route:' section — template broken?" >&2
    echo "--- rendered content (first 20 lines) ---" >&2
    head -20 "$OUT" >&2
    exit 1
fi

echo "alertmanager config rendered: $OUT ($(wc -l < "$OUT") lines)"

# Передаём управление настоящему alertmanager с готовым конфигом.
exec /bin/alertmanager \
    --config.file="$OUT" \
    --storage.path=/alertmanager \
    "$@"
