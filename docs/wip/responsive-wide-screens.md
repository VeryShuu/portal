# Фича: адаптация вёрстки под широкие экраны (1920×1080+)

## Цель

Убрать неэффективное использование ширины на больших экранах и разнобой
ширин контента между разделами. Ввести единую шкалу брейкпоинтов и ширин,
единый wrapper страницы и ступень уплотнения для широких экранов, чтобы на
1920×1080 контент выглядел сбалансированно (без «плавающей» узкой колонки и
без растянутых край-в-край таблиц).

## Контекст проблемы (зафиксировано при анализе)

Проверено вживую на портале (Playwright, viewport 1920×1080, вход `/auth/local`):

- **Home `/` и `/news`**: контент capped `max-width: 1280px`, центрируется →
  по ~200px пустоты с каждой стороны; карточные сетки разрежены.
- **Staff `/staff` (таблица)**: тянется край-в-край без `max-width` → колонки
  расползаются, большие пустоты между значениями.
- При навигации между разделами ширина контента **скачет** (1280 центр → full-bleed).

Корневые причины:
1. `frontend/src/composables/useBreakpoints.ts` — только `mobile <768`,
   `tablet 768–1024`; всё `≥1024` — единый «desktop», лишнего пространства не видит.
2. Разнобой `max-width`: токен `--layout-content-max: 1200px`
   (`frontend/src/styles/tokens.css:78`) есть, но страницы хардкодят 1200 / 1280 /
   1440 / 860 / 900 / без лимита.
3. Сетки с фиксированным `repeat(N)` не уплотняются:
   `pages/NewsListPage.vue:330` (3), `components/widgets/HomeNewsGrid.vue:54` (2),
   `components/KbListArticles.vue:101` (2).
4. Full-width таблицы без верхнего предела (`components/staff/StaffTableView.vue`).
5. Нет единой шкалы брейкпоинтов: в медиазапросах разбросаны
   600/640/720/768/860/900/960/1024/1100/1280; в `docs/` правил адаптива нет.

## Принятые решения (по мировым best-practices)

Развилки закрыты на основе общепринятых отраслевых стандартов (Tailwind/Bootstrap/
Material 3, типографика, современный CSS), а не по вкусу. Источники — в конце раздела.

### 1. Шкала брейкпоинтов = индустриальный стандарт (Tailwind)

`sm 640` · `md 768` · `lg 1024` · `xl 1280` · `2xl 1536`.
Де-факто стандарт; совпадает с уже встречающимися в проекте порогами 640/768/1024/1280.
Подход **mobile-first** (`min-width`), как рекомендуют Bootstrap/Tailwind/MDN.

### 2. Fluid-контейнер вместо «фикс. кап + margin auto»

Best-practice контейнер: `width: min(100% - 2*gutter, <max>)` + `margin-inline: auto`,
с **fluid-gutter** `clamp(16px, 4vw, 48px)`. Это снимает обе крайности (узкая
плавающая колонка ↔ растяжка край-в-край) — паттерн современных дашбордов
(GitHub/Linear/Vercel). Жёсткий `max-width` без fluid-полей не используем.

### 3. Три осознанных класса ширины

- **reading ≈ 768px** — проза (KB-статья, новость-детейл). Обоснование:
  оптимальная длина строки **45–75 символов** (типографика; ~66ch ⇒ ~720–800px).
  Текущие 860/900 чуть шире нормы — сводим к reading-токену.
- **standard ≈ 1280px** — большинство списков/страниц.
- **wide ≈ 1600px** — плотные сетки и таблицы (staff, photos, files, admin-списки).
  Заполняет 1920 без «пустых берегов», но не даёт строкам/таблицам растягиваться
  бесконечно (UX-правило ограничения line-length и плотности).

### 4. Сетки = intrinsic responsive (без ручных breakpoint'ов)

Стандарт современного CSS Grid: `repeat(auto-fill, minmax(<min>, 1fr))` вместо
фиксированного `repeat(N)`. Сетка сама добирает колонки по доступной ширине, число
колонок естественно ограничивается шириной контейнера (wide). Ручные `@media` для
числа колонок убираем где возможно. Рекомендуемые `min`: карточки новостей ≈ 320px,
KB ≈ 320px, staff-карточки ≈ 280px (уже так в `auto-fill`-сетках проекта).

### 5. Таблицы

Таблицу ограничиваем `wide`-контейнером; колонки сайзятся по контенту, без
edge-to-edge растяжки. Это устраняет «разорванные» строки на 1920.

### 6. Опционально (enhancement)

Fluid-spacing/typography через `clamp()` для плавного масштаба между вьюпортами —
по желанию, отдельным мелким шагом, не блокирует основной объём.

### Источники (best-practices)

- Tailwind CSS — Responsive Design (шкала брейкпоинтов, mobile-first).
- MDN — `min()` / `clamp()`, CSS Grid `minmax()`/`auto-fill`/`auto-fit`.
- Bootstrap — Breakpoints (mobile-first, container).
- Material Design 3 — Layout / Window size classes.
- Типографика: оптимальная длина строки 45–75 символов (Bringhurst; WCAG ~80
  символов как верхняя граница читабельности).

## Решения по ходу

- <дата>: <фиксировать отклонения от принятых решений и их причины по мере работы>
- Доохват пропущенных активных роутов (по итогам ревью реализации): три
  страницы оставались с off-scale хардкодами и давали скачок ширины между
  разделами — сведены к шкале:
  - `pages/KbArticlePage.vue` (просмотр KB-статьи): `.article-wrap` 900 и
    `.article-outer` 1200 → `var(--content-standard)`. Классифицирована как
    **standard**, а не reading: это документ с шапкой, sticky-сайдбаром вложений
    и табами (комментарии/версии/предложить правку), а не чистая проза как
    `NewsDetailPage`. Так нет скачка при `/kb` (standard) → статья.
  - `pages/MyFeedbackPage.vue` (список тикетов): 960 → `.u-page-wrap` (standard).
  - `pages/photos/MySharesPage.vue` (список шар): 900 + собственный `padding:24px`
    → `.u-page-wrap` (standard); padding убран (даёт `.app-content`).
  - Удалён мёртвый `pages/BookmarksPage.vue` (роут `/bookmarks` — redirect на
    `links?tab=my`, компонент нигде не рендерился) + его smoke-тест.

## План работ (этапы)

### Этап 1 — Токены (фундамент)
- [x] В `frontend/src/styles/tokens.css` ввести переменные:
      - брейкпоинты: `--bp-sm: 640px; --bp-md: 768px; --bp-lg: 1024px;
        --bp-xl: 1280px; --bp-2xl: 1536px;`
      - ширины контента: `--content-reading: 768px; --content-standard: 1280px;
        --content-wide: 1600px;`
      - fluid-gutter: `--page-gutter: clamp(16px, 4vw, 48px);`
- [x] `--layout-content-max` оставить алиасом на `--content-standard`
      (обратная совместимость со старым кодом).
- [x] Характеризующий контракт-тест шкалы: `tests/unit/layout-tokens.spec.ts`.

### Этап 2 — Единый wrapper (fluid-контейнер)
- [x] Переделать `.u-page-wrap` в `frontend/src/styles/utilities.css` на
      `width: min(100% - 2*var(--page-gutter), var(--content-standard));
      margin-inline: auto;` + модификаторы `--reading|--wide`, меняющие только
      max через локальную `--u-page-wrap-max` (→ `--content-reading|--content-wide`).
- [x] Комментарий: какой класс для какого типа страниц (reading=проза,
      standard=списки, wide=сетки/таблицы).
- [x] Контракт-тест wrapper'а добавлен в `tests/unit/layout-tokens.spec.ts`.

### Этап 3 — Миграция страниц на wrapper/токены (без скачков ширины)
- [x] `pages/HomePage.vue` (хардкод 1280 → standard, `.u-page-wrap`).
- [x] `pages/NewsListPage.vue`, `pages/NewsFormPage.vue` (standard, `.u-page-wrap`).
- [x] `pages/KbListPage.vue` (standard), `pages/KbArticleFormPage.vue` (reading),
      `pages/NewsDetailPage.vue` (reading) — `.u-page-wrap[--reading]`.
- [x] `pages/LinksAndBookmarksPage.vue` (standard), `pages/UserProfileView.vue`
      (standard; view-mode `!isOwn` → `--reading` вместо прежних 800px).
- [x] `pages/photos/PhotosIndexPage.vue`, `pages/photos/PublicFolderPage.vue`
      (wide через токен `var(--content-wide)` — grid/flex-шелл, без wrapper-класса).
- [x] `pages/AdminPage.vue` (wide, `.u-page-wrap--wide`) и `pages/FilesPage.vue`
      (wide через токен — flex-шелл с `height:100%`, добавлен `max-width`+`margin-inline:auto`).

> Подход: одноколоночные страницы → класс `.u-page-wrap` (fluid-gutter).
> Шелл-страницы (Photos/Files/PublicFolder, grid/flex с сайдбаром) → токен
> `var(--content-wide)` без wrapper-класса, чтобы не конфликтовать с flex/grid-механикой.

### Этап 4 — Сетки: intrinsic responsive (auto-fill/minmax)
- [x] `pages/NewsListPage.vue` — `repeat(3,...)` → `repeat(auto-fill, minmax(320px, 1fr))`.
- [x] `components/widgets/HomeNewsGrid.vue` — 2 кол. → `auto-fill, minmax(320px, 1fr)`.
- [x] `components/KbListArticles.vue` — 2 кол. → `auto-fill, minmax(320px, 1fr)`.
- [x] Удалены ручные `@media` для числа колонок (NewsList 1100/720, HomeNewsGrid 720, KbList 900).
- [ ] Главная: на `≥2xl` рассмотреть 2 колонки виджетов в сайд-колонке (опционально, отложено).

### Этап 5 — Staff-таблица
- [x] Страница `pages/StaffDirectoryPage.vue` (root `.staff-wrap`) обёрнута в
      `.u-page-wrap--wide` → весь раздел (head/filters/table/grid) capped 1600,
      центрирован; на 1920 таблица больше не тянется край-в-край. `StaffTableView`
      и плейсхолдер-таблица наследуют `width:100%` внутри 1600-контейнера (auto
      table-layout → колонки по контенту). Savebar `position:fixed` к вьюпорту —
      wrapper не обрезает.

### Этап 6 — JS-брейкпоинты
- [x] `frontend/src/composables/useBreakpoints.ts`: константы переименованы под
      CSS-шкалу (`BP_MD/LG/XL/2XL`), пороги `isMobile<md`, `isTablet md..lg` без
      изменений; добавлены `isWide (≥xl 1280)` / `isDesktopXl (≥2xl 1536)`.
      Потребители (`AppLayout` isMobile/isTablet, `useStaffView`/`RoomGrid`
      isMobile) деструктурируют только нужное — обратно совместимо, сворачивание
      сайдбара не затронуто.

### Этап 7 — Унификация магических медиазапросов
- [x] Off-scale `@media` в затронутых файлах сведены к шкале (literal-значения,
      т.к. CSS custom properties не работают в условии `@media`):
      HomePage `1100→1024`, NewsFormPage `1100→1024`, UserProfileView `960→1024`,
      PhotosIndexPage `900→1024` (collapse сайдбар/грид → `lg`); KbListPage
      `860→768`, NewsDetailPage `720→768` (→ `md`). On-scale (640/768/1024/1280)
      и микро-брейк `480` (скрытие столбцов staff, нет аналога в шкале) — без
      изменений.

### Этап 8 — Документация
- [x] Создан `docs/ui-layout.md` (шкала брейкпоинтов, три класса ширины,
      `.u-page-wrap` + когда класс/токен, intrinsic-сетки, `useBreakpoints`,
      контракт-тест). Зарегистрирован в `docs/README.md` (роутер + раздел
      «Модули»). ADR не понадобился (решения зафиксированы в самом плане + доке).

## Чеклист (DoD)

- [x] миграция / модель / схема — N/A (чисто фронтовая фича)
- [x] сервис (бизнес-логика) — N/A
- [x] API endpoint + регистрация — N/A
- [x] unit-тесты — контракт-тест шкалы/wrapper `tests/unit/layout-tokens.spec.ts`
      (CSS-only фича; jsdom не считает layout → проверяем CSS-контракт).
- [x] frontend (токены / wrapper / страницы / сетки) — этапы 1–7
- [x] i18n (ru + en) — N/A (user-facing строки не добавляются), `i18n:check` OK
- [x] lint + typecheck + tests pass:
      `lint:check` ✓, `typecheck` ✓, `test:unit` ✓ (84 файла / 1262 теста),
      `i18n:check` ✓ (1807 ключей).
- [x] визуальная проверка на 1920×1080 (Playwright, `/auth/local`):
      home (standard, 2 кол.), news (standard, intrinsic-grid), kb (standard,
      2 кол.), staff (wide, центр, без edge-to-edge), photos (wide), files
      (wide, был full-bleed), admin (wide). Скачков ширины нет, console 0 errors.
- [x] обновлены docs/ (этап 8: `docs/ui-layout.md` + индекс `docs/README.md`)

## Грабли / контекст

- Вход для проверки UI: `/auth/local` (backdoor, без публичной ссылки).
- Naive UI сам рисует часть таблиц/лэйаутов — проверять, что наши `max-width`
  не конфликтуют с внутренними стилями `n-data-table` (использовать `:deep()`).
- `scrollbar-gutter: stable` в `.app-content` (`AppLayout.vue`) уже резервирует
  место под скролл — учитывать при расчёте gutters.
- `HomePage.vue` правился пользователем во время анализа — перед правкой
  перечитать актуальную версию.
- Reading-ширина — **осознанная** ступень (комфорт чтения, 45–75 символов в
  строке); сводим текущие 860/900 к `--content-reading ≈ 768px`, не раздувать
  до standard. После правки проверить, что широкие медиа (картинки/таблицы внутри
  статьи) не ломают узкую колонку.
- Менять только ширины/сетки/брейкпоинты; стек и компоненты не трогать
  (Naive UI зафиксирован).
