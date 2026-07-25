FROM postgres:16

# NOTE: build context = корень репо (см. docker-compose.yml, ADR-046). Раньше
# context был ./postgres, но чтобы запечь backend/migrations/init.sql в образ
# (для prod-контура без клона репо), context поднят до ".". Пути COPY ниже —
# относительно корня репо.

RUN sed -i 's|URIs: http://deb.debian.org|URIs: http://mirror.yandex.ru|g' /etc/apt/sources.list.d/debian.sources 2>/dev/null; \
    sed -i 's|http://deb.debian.org|http://mirror.yandex.ru|g' /etc/apt/sources.list 2>/dev/null; \
    apt-get update \
    && apt-get install -y --no-install-recommends \
        hunspell-ru \
    && rm -rf /var/lib/apt/lists/*

RUN PGSHARE=$(pg_config --sharedir) \
    && mkdir -p "${PGSHARE}/tsearch_data" \
    && cp /usr/share/hunspell/ru_RU.dic "${PGSHARE}/tsearch_data/russian.dict" \
    && cp /usr/share/hunspell/ru_RU.aff "${PGSHARE}/tsearch_data/russian.affix"

COPY postgres/hunspell/russian.stop /tmp/russian.stop
RUN PGSHARE=$(pg_config --sharedir) \
    && cp /tmp/russian.stop "${PGSHARE}/tsearch_data/russian.stop"

# init.sql: расширения + FTS-конфиг russian_hunspell. Запекается в образ
# (раньше bind-mount'ился из клона репо на проде — см. ADR-046).
# Скрипты в /docker-entrypoint-initdb.d выполняются ТОЛЬКО при первом старте
# (пустой PGDATA), так что на уже развёрнутых стендах повторного срабатывания
# не будет — это безопасно.
COPY backend/migrations/init.sql /docker-entrypoint-initdb.d/01-init.sql
