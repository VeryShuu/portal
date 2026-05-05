FROM mcr.microsoft.com/playwright/python:v1.44.0-jammy

WORKDIR /app

RUN groupadd -r pptruser && useradd -r -g pptruser -G audio,video pptruser \
    && mkdir -p /home/pptruser/Downloads \
    && chown -R pptruser:pptruser /home/pptruser \
    && chown -R pptruser:pptruser /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

RUN chown -R pptruser:pptruser /app

USER pptruser

EXPOSE 9000

CMD ["python", "main.py"]
