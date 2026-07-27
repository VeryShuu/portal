# =============================================================================
# storage-collector — лёгкий sidecar (alpine + busybox crond), собирает размеры
# папок данных портала, Docker json-file логов и named volumes в Prometheus
# textfile-формат, который затем читает node-exporter.
#
# Не открывает портов. Монтирует /:/host:ro (для du по host-папкам и чтения
# config.v2.json контейнеров) и ./monitoring/textfile:/textfile (rw, куда
# складывает storage.prom).
#
# Образ минимальный: alpine:3.20 (~7MB) + jq (для парсинга config.v2.json).
# =============================================================================
# pinned 2026-07-26
FROM alpine:3.20@sha256:d9e853e87e55526f6b2917df91a2115c36dd7c696a35be12163d44e6e2a4b6bc

# jq — для надёжного чтения .Name из config.v2.json. du/awk/sed/crond — в busybox.
# tini — корректная репликация сигналов дочернему crond (PID 1 не zombie).
RUN apk add --no-cache jq tini

COPY collect.sh  /usr/local/bin/collect.sh
COPY crontab      /etc/crontabs/storage-collector

RUN chmod +x /usr/local/bin/collect.sh \
    && chmod 600 /etc/crontabs/storage-collector

# Первый сбор сразу при старте — чтобы метрики появились без ожидания 5 мин.
# Затем crond крутит расписание.
CMD ["sh", "-c", "/usr/local/bin/collect.sh 2>/dev/null; exec crond -f -l 8"]

ENTRYPOINT ["/sbin/tini", "--"]
