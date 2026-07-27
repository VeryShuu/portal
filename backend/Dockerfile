# pinned 2026-07-26
FROM python:3.12-slim@sha256:57cd7c3a7a273101a6485ba99423ee568157882804b1124b4dd04266317710de AS build-deps

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_RETRIES=10 \
    PIP_DEFAULT_TIMEOUT=120 \
    DEBIAN_FRONTEND=noninteractive

# Нативный retry apt-get вместо «sleep + повтор» — см. REVIEW-5.1.
RUN echo 'Acquire::Retries "10";' > /etc/apt/apt.conf.d/80-retries \
    && echo 'Acquire::http::Timeout "60";' >> /etc/apt/apt.conf.d/80-retries \
    && echo 'Acquire::https::Timeout "60";' >> /etc/apt/apt.conf.d/80-retries \
    && (sed -i 's|URIs: http://deb.debian.org|URIs: http://mirror.yandex.ru|g' /etc/apt/sources.list.d/debian.sources 2>/dev/null || true) \
    && (sed -i 's|http://deb.debian.org|http://mirror.yandex.ru|g' /etc/apt/sources.list 2>/dev/null || true)

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        libmagic-dev \
        libpq-dev \
        libheif-dev \
        libjpeg62-turbo-dev \
        zlib1g-dev \
        libwebp-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

FROM build-deps AS runtime-base

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        curl \
        gosu \
        redis-tools \
        libmagic1 \
        libpq5 \
        libheif1 \
        libde265-0 \
        libjpeg62-turbo \
        zlib1g \
        libwebp7 \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Российские доверенные CA (Минцифры). Не входят в Mozilla CA Bundle Debian —
# без этого исходящие HTTPS к российским сервисам (MAX Bot API, Госуслуги и т.д.)
# падают с CERTIFICATE_VERIFY_FAILED. Промежуточные сертификаты сюда НЕ кладём:
# серверы отдают их в TLS-handshake, OpenSSL сам соберёт chain leaf → sub → root.
# См. backend/certs/README.md.
COPY certs/*.crt /usr/local/share/ca-certificates/
RUN update-ca-certificates

FROM build-deps AS prod-builder

WORKDIR /app
COPY pyproject.toml ./
RUN pip install --upgrade pip && pip install --prefix=/install ".[prod]"

FROM runtime-base AS test

WORKDIR /app
COPY pyproject.toml ./
RUN pip install --upgrade pip \
    && pip install ".[dev]" \
    && pip install aiosqlite freezegun
COPY app ./app
COPY tests ./tests
COPY scripts ./scripts
COPY migrations ./migrations
COPY alembic.ini ./
RUN chmod +x /app/scripts/entrypoint.sh /app/scripts/migrate.sh /app/scripts/run_pytest_unit.sh /app/scripts/run_pip_audit.sh
EXPOSE 8000

# apt-packages, Russian CA certs, ENV и apt-mirror наследуются из runtime-base —
# держим весь apt-установок и update-ca-certificates в одном месте (см. REVIEW M15).
FROM runtime-base AS production

COPY --from=prod-builder /install /usr/local

WORKDIR /app
COPY app ./app
COPY migrations ./migrations
COPY scripts ./scripts
COPY alembic.ini ./
COPY pyproject.toml ./

RUN addgroup --system --gid 1001 portal \
    && adduser --system --uid 1001 --gid 1001 --no-create-home portal \
    && mkdir -p /data \
    && chmod +x /app/scripts/entrypoint.sh /app/scripts/migrate.sh

EXPOSE 8000

ENTRYPOINT ["/app/scripts/entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--limit-concurrency", "100"]
