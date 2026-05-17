FROM python:3.12-slim AS build-deps

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
    && echo 'Acquire::https::Timeout "60";' >> /etc/apt/apt.conf.d/80-retries

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
    && rm -rf /var/lib/apt/lists/*

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

FROM python:3.12-slim AS production

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive

# Нативный retry apt-get вместо «sleep + повтор» — см. REVIEW-5.1.
RUN echo 'Acquire::Retries "10";' > /etc/apt/apt.conf.d/80-retries \
    && echo 'Acquire::http::Timeout "60";' >> /etc/apt/apt.conf.d/80-retries \
    && echo 'Acquire::https::Timeout "60";' >> /etc/apt/apt.conf.d/80-retries

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
    && rm -rf /var/lib/apt/lists/*

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
