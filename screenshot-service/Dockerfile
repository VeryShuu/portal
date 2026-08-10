# pinned 2026-07-28
# Базовый образ Playwright должен совпадать по версии с requirements.txt (playwright==X.Y.Z),
# иначе браузеры в образе не совместимы с Python-dep → "Executable doesn't exist at /ms-playwright/…"
# (compose-smoke regression после #29: pip playwright 1.44→1.61 без обновления базового образа).
# Dependabot не умеет обновлять MCR-теги → при bump playwright в requirements.txt
# ОБЯЗАТЕЛЬНО поднять и этот тег (CI-чек playwright-sync-check ловит рассинхрон автоматически).
FROM mcr.microsoft.com/playwright/python:v1.62.0-jammy@sha256:017530b316b85f71b3f0989310393a9095253820e77e9ed94aa3b7d7eb5ecd16

WORKDIR /app

RUN groupadd -r pptruser && useradd -r -g pptruser -G audio,video pptruser \
    && mkdir -p /home/pptruser/Downloads \
    && chown -R pptruser:pptruser /home/pptruser \
    && chown -R pptruser:pptruser /app

COPY requirements.txt .
ENV PIP_RETRIES=10 \
    PIP_DEFAULT_TIMEOUT=120
RUN pip install --no-cache-dir -r requirements.txt \
    || (sleep 10 && pip install --no-cache-dir -r requirements.txt) \
    || (sleep 20 && pip install --no-cache-dir -r requirements.txt)

# Копируем runtime-модули сервиса (main.py + helpers). Список явный: test_*.py
# и pytest.ini/requirements-dev.txt — это CI-only артефакты, в образе не нужны.
# При добавлении нового helper-модуля добавить его сюда же.
COPY main.py cookie_utils.py ./

RUN chown -R pptruser:pptruser /app

USER pptruser

EXPOSE 9000

CMD ["python", "main.py"]
