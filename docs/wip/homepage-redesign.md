# Фича: Редизайн главной страницы портала МАГЭ

> **Эксперимент** (ветка `feat/homepage-redesign`). Может быть отменён. Все изменения
> изолированы в ветке; единственная backend-правка (branding hero-bg) — JSON-файл,
> БД-миграций НЕТ, откатывается `git revert` + удалением файлов `/data/branding/hero-bg-*`.

## Цель
Повысить удобство главной страницы: современный flat-UI, единый стиль карточек,
фирменная navy-палитра МАГЭ (#1F4E8C / #2F6CB5), увеличенный Hero с настраиваемым
фоном по времени суток. Только UI/UX + одно контролируемое расширение branding.

## Решения по ходу
- **2026-08-07:** Красный `#d8262c` остаётся global primary (кнопки, активные пункты
  меню, runtime-accent). Navy — декоративный/фоновый слой Hero и секций. Глобальную
  brand-систему НЕ ломаем. (Уточнено пользователем.)
- **2026-08-07:** Hero stats card («Новости/Встречи/Мои задачи») убрана — нет
  endpoint'а под эти числа, ТЗ запрещает менять API. Hero = приветствие + дата + фон.
- **2026-08-07:** Hero фон — admin загружает 3 фото (утро/день/вечер) + настраивает
  час-границы слотов через BrandingTab. Нет фото → CSS-градиент fallback по времени.
  Расширение branding-инфры (как login-bg), НЕ БД-миграция. (Уточнено пользователем.)
- **2026-08-07:** «Быстрые ссылки» (ТЗ п.6) — на основе персональных закладок
  (`GET /bookmarks`). Пусто → блок скрыт.

## Чеклист (DoD)
- [x] Этап 0: ветка `feat/homepage-redesign` + этот план
- [x] Этап 1: Backend branding — `hero_morning/day/evening_hour` (6/12/18) + 3 hero-bg
      assets (schema, 9 routes, bootstrap, openapi.json реген)
- [x] Этап 1: Backend тесты branding (3 kinds upload/get/delete + hour validation + audit) — 116 pass
- [x] Этап 2: Frontend токены МАГЭ (`tokens.css` `--color-mage-*` + `--radius-card/hero` +
      `--shadow-soft` + dark overrides)
- [x] Этап 3: `HeroBlock.vue` переработка (высота 240px, radius 20, фон-фото/градиент
      по heroSlot, per-time subtitle)
- [x] Этап 4: `stores/branding.ts` (BrandingAsset + ASSET_FLAG) + `BrandingTab.vue`
      (3 hero-bg uploads + 3 hour inputs)
- [x] Этап 5: `NewsCard.vue` оформление (padding 20, radius 16, cover 200px object-fit
      cover, footer в одну строку, тень --shadow-soft)
- [x] Этап 6: Унификация `.widget` (radius 16, padding 20, mage-palette) для всех виджетов
- [x] Этап 7: `QuickServicesWidget` (плитки 56px), `MeetingsWidget` empty-state компакт,
      `BirthdaysWidget` список вместо карусели, `PhotosWidget` крупнее, новый
      `QuickLinksWidget` (bookmarks)
- [x] Этап 8: Адаптивность 1366/1440/1600 (media queries)
- [x] Этап 9: Frontend unit-тесты (Hero/NewsCard/Meetings/Birthdays/QuickLinks) — 2278 pass +
      i18n parity (ru+en, 2311 ключей)
- [x] Этап 10: drift-checks (`check-drift.sh --check` зелёный), `ci_lint.sh` зелёный,
      typecheck/build зелёные, push ветки + PR #88 создан.
      ⏳ Ожидает CI (16 обязательных чеков). НЕ Merge — решение пользователя.

## Грабли / контекст
- **16 обязательных CI-чеков** — drift (openapi/types/tests) критичны, гонять
  `./scripts/check-drift.sh --fix` до пуша.
- **Dark mode first-class** — все mage-стили покрыть `[data-theme='dark']` overrides.
- **red-accent runtime override НЕ ломать** — mage-navy отдельный слой, не трогает
  `--color-brand-red*` и `naive-theme.primaryColor`.
- **Backend-правка обратима**: branding — JSON в `/data/branding/settings.json`,
  ассеты в `/data/branding/hero-bg-*`. Откат = `git revert` + `rm` файлов.
- **Главная — не единственный consumer branding**: login-bg использует тот же механизм
  (клонировать паттерн, не менять сигнатуры существующих хендлеров).
- **Структура меню, маршруты, API-контракты, бизнес-логика виджетов** — не трогать.
