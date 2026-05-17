FROM postgres:16

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

COPY hunspell/russian.stop /tmp/russian.stop
RUN PGSHARE=$(pg_config --sharedir) \
    && cp /tmp/russian.stop "${PGSHARE}/tsearch_data/russian.stop"
