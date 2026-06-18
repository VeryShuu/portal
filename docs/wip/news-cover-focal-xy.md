# Фича: произвольная точка фокуса обложки новости (focal x/y)

> **Когда читать:** возобновляешь незавершённую многосессионную задачу — этот
> план хранит контекст между сессиями (handoff).
> **Правила:** раздел «Работа между сессиями» в `../../AGENTS.md`.
> Создаётся, как только ясно, что задача не закроется за одну сессию; удаляется
> после мёржа фичи (чтобы `wip/` отражал только активную работу).

## Цель

Заменить enum-фокус обложки (`cover_focal_point` ∈ `top/center/bottom`, по
горизонтали всегда центр) на произвольную точку фокуса в процентах
(`cover_focal_x` / `cover_focal_y`, 0–100) с draggable-маркером на превью.
Кадрирование по-прежнему через CSS `object-position` — картинка и
WebP/AVIF-варианты не пересоздаются.

## Решения по ходу

- 2026-06-18: координаты — целые `SMALLINT` 0–100 (1% шага визуально достаточно),
  не `NUMERIC`.
- 2026-06-18: UI — draggable-маркер поверх превью (не два input-поля).
- 2026-06-18: `NULL` x/y = центр (50/50) — дефолт без бэкфилла каждой строки.
- 2026-06-18: `cover_focal_point` дропаем в той же миграции `072`. Деплой =
  рестарт одного backend-контейнера с авто-миграцией на старте (`migrate.sh`),
  совместного существования старого/нового кода нет → строгий zero-downtime-дроп
  отдельной миграцией не нужен.
- 2026-06-18: email-обложка (`build_email_cover_jpeg`) и перегенерация
  WebP/AVIF — вне scope (object-position там не применяется).

## Чеклист (DoD)

### БД / модель / схема
- [ ] Миграция `072_news_cover_focal_xy`:
  - [ ] `ADD COLUMN cover_focal_x SMALLINT` + `CHECK (0..100)`
  - [ ] `ADD COLUMN cover_focal_y SMALLINT` + `CHECK (0..100)`
  - [ ] backfill из enum: `top→(50,0)`, `bottom→(50,100)`, `center`/`NULL`→`NULL`
  - [ ] `DROP COLUMN cover_focal_point`
  - [ ] downgrade: обратное преобразование (x=50,y=0→top; y=100→bottom; иначе center)
- [ ] `app/models/news.py`: убрать `cover_focal_point`, добавить `cover_focal_x`/`cover_focal_y` (`Mapped[int | None]`)
- [ ] `app/schemas/news.py`:
  - [ ] `NewsPublic`: `cover_focal_point` → `cover_focal_x`/`cover_focal_y`
  - [ ] `NewsCreate`/`NewsUpdate`: enum-валидатор → диапазон 0–100 (оба поля)

### Сервис (бизнес-логика)
- [ ] `app/services/news/crud.py`: в `create_news` (`cover_focal_point=`) и списке
      полей `update_news` заменить на `cover_focal_x`/`cover_focal_y`

### API
- [ ] Новый endpoint не нужен (поля едут через существующие POST/PUT `/news`)
- [ ] Перегенерировать `openapi.json` (`cd backend && python -m scripts.export_openapi`)

### unit-тесты (backend)
- [ ] Обновить упоминания `cover_focal_point`: `test_news_routes.py`,
      `test_news_service.py`, `tests/integration/test_news_api.py`,
      `tests/integration/test_migrations.py`
- [ ] Валидация диапазона: 0/100 → ok, -1/101 → 422

### frontend
- [ ] Новый хелпер `src/utils/coverFocal.ts`: `focalObjectPosition(x, y)`
- [ ] Применить хелпер вместо дублей: `components/news/NewsCard.vue`,
      `pages/NewsDetailPage.vue`, `components/news/NewsCoverUpload.vue`
- [ ] `NewsCoverUpload.vue`: drag-маркер на превью (rect→%, кламп 0–100,
      стрелки для a11y, дебаунс `PUT /news/{id}` на отпускании); `defineModel`
      `focalPoint` → `focalX`/`focalY`
- [ ] `components/news/NewsFormSettingsCard.vue`, `pages/composables/useNewsFormState.ts`,
      `pages/composables/newsFormMappers.ts` (`toFocalPoint`), `api/news.ts` (типы):
      single focal → x/y
- [ ] `npm run gen:types`

### i18n (ru + en)
- [ ] Убрать `news.form.focalTop/focalCenter/focalBottom`
- [ ] Обновить `news.form.coverFocalHint` («Перетащите точку…»), оставить `coverFocal`

### unit-тесты (frontend)
- [ ] Юнит на `coverFocal.ts` (включая null→центр)
- [ ] Обновить `news-form-page.spec.ts`, `cov2-*-news*`, smoke-специи
- [ ] Тест: клик/драг по превью → корректные x/y и `object-position`

### Качество
- [ ] backend: `ruff check . && mypy app && pytest tests/unit`
- [ ] frontend: `npm run lint:check && npm run typecheck && npm run test:unit && npm run i18n:check`

### docs
- [ ] `docs/news.md` (раздел «Обложка и адаптивные варианты» + модель данных)
- [ ] `docs/db-schema.md` (колонки `news.cover_focal_*`)
- [ ] `*.generated.md` — авто-генерация (db-schema/api-contracts)

## Грабли / контекст

- Логика `object-position` сейчас **продублирована в 3 местах** (NewsCard,
  NewsDetailPage, NewsCoverUpload) — обязательно вынести в `coverFocal.ts`,
  иначе разъедется.
- `cover_focal_point` валидируется в схемах в ДВУХ местах (NewsCreate `~:163`,
  NewsUpdate `~:188`) — не забыть оба.
- `setFocal` в `NewsCoverUpload.vue` шлёт `PUT /news/{id}` сразу в режиме
  редактирования; в режиме создания — копится в форме. Для drag сделать дебаунс,
  чтобы не слать PUT на каждый mousemove.
- Превью-контейнер и карточка — фиксированный `aspect-ratio: 16/9`; маркер
  позиционировать относительно этого контейнера, не самого `<img>`.
- `cover_focal_point` встречается в `types.gen.d.ts` (4 места) — уйдёт после
  `gen:types`, руками не править (файл в `.gitignore`).
