FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        curl \
        libmagic1 \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

FROM base AS builder

COPY pyproject.toml .

RUN pip install --upgrade pip \
    && pip install ".[prod]" --target /install

FROM base AS production

COPY --from=builder /install /usr/local/lib/python3.12/site-packages

RUN playwright install --with-deps chromium

COPY . .

RUN addgroup --system --gid 1001 portal \
    && adduser --system --uid 1001 --gid 1001 --no-create-home portal \
    && mkdir -p /data/avatars \
    && chown -R portal:portal /data

USER portal

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "2", "--limit-concurrency", "100"]
