# Фича: Расширение аналитики (раздел A — данные уже собираются)

## Цель
Расширить админ-вкладку «Аналитика» новыми срезами на уже собираемых данных
(audit_log / kb_articles / news / feedback), без новой телеметрии и миграций.

## Объём (раздел A, 7 пунктов)
1. Селектор периода (7/30/90/365) — драйвит top-*, departments и временные ряды dashboard.
2. WAU/MAU + тренд активных пользователей (distinct user_id из audit_log).
3. Контент-гигиена: KB/новости с 0 просмотров или «застойные» (по updated_at).
4. Тренд загрузок (files.file_uploaded, kb.file_upload, photos.photo_uploaded).
5. Статистика «Обращений» (feedback): счётчики по статусам + среднее время первого ответа.
6. Drill-down sparkline по ярлыку/файлу (links.visited / *_downloaded по resource_id).
7. Экспорт таблиц аналитики в CSV/XLSX.

## Решения по ходу
- `/dashboard` получает `days` (default 14) — влияет ТОЛЬКО на временные ряды; KPI-окна
  («за 30 дн», «за сутки», «за 1 ч») остаются фиксированными по определению.
- WAU/MAU = distinct user_id из audit_log за 7/30 дней (метрика активности, не last_login).
- Тренд активных и тренд загрузок добавлены в `dashboard.series` (один период-driven endpoint).
- Stale-content: один endpoint, объединяет KB+news (`kind`), published & not-deleted,
  view_count=0 ИЛИ updated_at < cutoff; сортировка view_count ASC, updated_at ASC.
- Feedback stats читается прямо из таблиц feedback/feedback_replies (модель уже есть).
- Resource-trend: `kind=link|file`, возвращает list[DailyPoint].
- Export: generic CSV (stdlib) + XLSX (openpyxl, как в directories), per-dataset.

## Чеклист (DoD)
- [x] schemas/analytics.py — новые модели
- [x] services/analytics_repo.py — новые запросы
- [x] api/analytics.py — новые endpoints + days на dashboard
- [x] unit-тесты backend
- [x] frontend: api/analytics.ts + queries/admin.ts + keys.ts
- [x] frontend: AnalyticsTab.vue (селектор, новые карточки, drill-down, экспорт)
- [x] i18n ru + en
- [x] frontend unit-тесты
- [x] lint + typecheck + tests + i18n:check
- [x] docs/analytics.md + regen openapi/api-contracts

## Грабли / контекст
- Тесты analytics передают строки как MagicMock только с `__getitem__` → в роутах
  обращаться через `r["key"]`, не через `dict(r)`/`model_validate(dict(r))`.
- audit_log партиционирован по месяцам; запросы on-demand (ок для ~300 польз./12 мес.).
- Upload-события: `files.file_uploaded`, `kb.file_upload`, `photos.photo_uploaded`.
- Коллизия имён схем: `app.schemas.kb.FeedbackStats` уже существует → analytics-схему
  назвали `FeedbackStatsOut`, иначе FastAPI fully-qualify обе и ломается
  `kb.ts: components['schemas']['FeedbackStats']`. После regen openapi обязательно
  `npm run gen:types` (types.gen.d.ts в .gitignore).
