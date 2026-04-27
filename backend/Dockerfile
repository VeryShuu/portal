FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        curl \
        libmagic1 \
        libpq-dev \
        build-essential \
        libheif1 \
        libde265-0 \
        libjpeg62-turbo \
        zlib1g \
        libwebp7 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

FROM base AS test

COPY pyproject.toml ./
COPY app ./app
COPY tests ./tests
COPY scripts ./scripts
COPY migrations ./migrations
COPY alembic.ini ./

RUN pip install --upgrade pip \
    && pip install ".[dev]"

FROM base AS production

COPY pyproject.toml ./
COPY app ./app

RUN pip install --upgrade pip \
    && pip install ".[prod]"

RUN playwright install --with-deps chromium

COPY migrations ./migrations
COPY scripts ./scripts
COPY alembic.ini ./

RUN addgroup --system --gid 1001 portal \
    && adduser --system --uid 1001 --gid 1001 --no-create-home portal \
    && mkdir -p /data/avatars \
    && chown -R portal:portal /data /app /ms-playwright 2>/dev/null || true \
    && chmod +x /app/scripts/entrypoint.sh /app/scripts/migrate.sh

USER portal

EXPOSE 8000

CMD ["/app/scripts/entrypoint.sh"]
