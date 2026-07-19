# Доверенные CA для outbound HTTPS

Сертификаты, не входящие в Mozilla CA Bundle (Debian `ca-certificates`), но
необходимые для исходящих HTTPS-запросов из backend:

- **`russian_trusted_root_ca.pem`** — корневой сертификат Минцифры
  (The Ministry of Digital Development and Communications).
  Источник: https://gu-st.ru/content/Other/doc/russian_trusted_root_ca.cer
  (официальная страница: https://www.gosuslugi.ru/crt).

  Нужен для проверки TLS-сертификатов российских сервисов: MAX Bot API
  (`platform-api2.max.ru`), и любых других, подписанных через Russian Trusted
  Sub CA.

Промежуточные сертификаты (Sub CA) сюда **НЕ** кладём: серверы отдают их в
TLS-handshake, и OpenSSL/httpx сами собирают chain `leaf → sub CA → root CA`
при наличии Root CA в trust store. Это правильнее, чем хардкодить промежуточные
сертификаты, которые Минцифры периодически ротирует.

## Установка в Docker-образ

`backend/Dockerfile` копирует сертификаты из этой папки в
`/usr/local/share/ca-certificates/` и запускает `update-ca-certificates` на
этапах `runtime-base` и `production`. После этого они автоматически попадают
в `/etc/ssl/certs/ca-certificates.crt` и видны всем приложениям (httpx, aiohttp,
requests, etc.) — никаких `verify=False` или ручной передачи `cafile`.

## Обновление

Если сертификат Минцифры отзовут или заменят — перезалить `.pem` сюда,
пересобрать образ backend/worker (`docker compose build backend worker`).
Проверка: `openssl x509 -in russian_trusted_root_ca.pem -noout -subject`.
