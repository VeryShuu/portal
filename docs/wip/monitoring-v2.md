# Фича: Monitoring v2 — модернизация схемы observability-стека

## Цель
Обновить схему работы стека мониторинга после обновления версий (PR #59:
Prometheus 3.13 / Grafana 13.1 / Alertmanager 0.33): закрыть слепые зоны
(метрики контейнеров, TLS-сертификаты, внешние пробы), ускорить доставку
алертов (Matrix), осовременить дашборды (Grafana 13, drill-down, SLO) и
починить найденные дефекты (подстановка токена, латентность-гистограмма).

## Решения по ходу
- 2026-08-16: полный анализ + план утверждены пользователем («начинай с первого
  этапа и продолжай до конца»). Порядок: 1→2→3→4→6→5→7 (recording rules до
  дашбордов — SLO-панель зависит от них).
- 2026-08-16: cAdvisor отдельным контейнером (а не встроенный в Alloy
  prometheus.exporter.cadvisor) — Alloy не имеет монтировок /,/sys, расширение
  поверхности монтировок Alloy ради экспортера хуже изолированного сервиса.
- 2026-08-16: Matrix-bridge (matrix-webhook) за compose-profile `matrix` —
  опциональный сервис, не поднимается без явного включения.
- 2026-08-16: плагин Logs Drilldown — opt-in через env (интранет может не
  иметь доступа к grafana.com).

## Чеклист (DoD) — ВЫПОЛНЕН (2026-08-16, ветка feat/monitoring-v2)
- [x] Этап 0: обновление версий стека (PR #59, смёржен)
- [x] Этап 1: харденинг — render-prometheus.sh (токен, вырезание auth-блока,
      promtool fail-fast), MONITORING_BIND=127.0.0.1 (9 портов),
      GRAFANA_ADMIN_PASSWORD, бэкап-чеклист deploy.md
- [x] Этап 2: cAdvisor v0.55.1 (gcr.io — новее нет), labeldrop контейнерных
      лейблов, PortalContainerRestartLoop + CadvisorDown, 3 панели
      (PortalContainerGone отвергнут живым тестом — cadvisor удаляет серию
      остановленного контейнера за ~20с)
- [x] Этап 3: blackbox v0.28.0 (prom/, монтировать в config.yml!),
      file_sd из BLACKBOX_TARGETS* (генерация в render-скрипте),
      PortalExternalProbeFailed/PortalCertExpirySoon/Critical, NGINX_SCRAPE_URI
- [x] Этап 4: matrix-alertmanager bridge (profile matrix, jaywink),
      #@matrix-маркеры в alertmanager.yml + вырезание в render-скрипте
- [x] Этап 6: recording.yml (6 правил), pattern-ingester target (НЕ входит
      в default all!), derived field request_id→Logs-дашборд,
      GRAFANA_INSTALL_PLUGINS opt-in
- [x] Этап 5: RED на recording rules, переменная handler, SLO row,
      кросс-линки; ре-экспорт Grafana 13 — модель идентична (schemaVersion
      не меняется), визуальная проверка Playwright
- [x] Этап 7: latency() с полными бакетами (highr-дубль убран),
      http_metrics.py hooks (keycloak/nextcloud/matrix/max),
      portal_arq_job_duration_ms_total counter; ci_lint OK, 4520 unit OK,
      diff-coverage OK
- [x] Все конфиги валидны; финальный smoke — см. ниже

## Грабли / контекст
- ${PORTAL_METRICS_TOKEN} в prometheus.yml Prometheus НЕ раскрывает (env в
  конфиге не поддерживается никогда) — нужен entrypoint-рендер (этап 1).
- При пустом токене authorization-блок надо УДАЛЯТЬ, иначе promtool/рельні
  могут отвергнуть пустые credentials (проверить поведение).
- Alertmanager 0.27+ и 0.33+ отвергают пустой to: в email-конфиге — placeholder
  уже реализован в render-alertmanager.sh (PR #59).
- Grafana admin password из env действует только на свежий volume.
- Плагин grafana-lokiexplore-app качается с grafana.com при старте — на проде
  может не иметь доступа, потому opt-in.
- schemaVersion дашбордов 39 (экспорт Grafana 11.2) — ре-экспорт через API
  Grafana 13 на dev-машине (свежий volume + GRAFANA_ADMIN_PASSWORD).
- Проверка Loki-rules путей: rules/fake/<file>.yaml (tenant `fake`).
- SLO-цели не утверждены пользователем — панель с параметрами по умолчанию
  (99.5% / p99<2s), легко правится в UI.

## Открытые вопросы (к пользователю)
- Доступен ли продову grafana.com (плагин Logs Drilldown)?
- Мониторить бэкапы (корп. система) изнутри — вне скоупа, оставлено как есть.
- «Сборки» = сбор метрик или CI? (принято: сбор метрик/логов)

## Итог финального smoke-теста (2026-08-16, dev)
- 12/12 таргетов UP (вкл. cadvisor + blackbox-пробу dev-таргета), 50 правил
- /metrics: полные бакеты latency (288 строк), highr удалён, http_client
  метрики объявлены, ARQ-конвейер доказан end-to-end (enqueue → Redis-hash →
  гидрация → Prometheus: ms_total=24, jobs started/succeeded=1)
- SLO = 1; Loki ready; Grafana/Alertmanager 200
- ⚠️ patterns-API: роутится (валидация селекторов работает), но на dev-данных
  возвращает 404-с-пустым-телом на валидный селектор — паттерны не накопились
  или фича требует реального потребителя (плагин Logs Drilldown). Флаг
  оставлен (безвреден); на проде проверить после установки плагина, при
  404 — флаг можно убрать.
- Открытая находка (вне скоупа): ARQ-метрики считают только enqueued-задачи;
  кроны резолвятся по строке-пути к необёрнутым функциям (осознанно для
  refresh/heartbeat — иначе флуд 5с-кронов). При желании считать кроны —
  отдельная задача (обёртка cron-функций + фильтр шумных).
