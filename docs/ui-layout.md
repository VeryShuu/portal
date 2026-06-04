# UI Layout — брейкпоинты и ширины контента

> **Когда читать:** вёрстка новой страницы/раздела, выбор ширины контента, адаптив
> под широкие экраны (1920×1080+), правка `@media`-запросов, добавление сеток.
> **Ключевой код:** `./frontend/src/styles/tokens.css` (шкала),
> `./frontend/src/styles/utilities.css` (`.u-page-wrap`),
> `./frontend/src/composables/useBreakpoints.ts` (JS-флаги),
> `./frontend/tests/unit/layout-tokens.spec.ts` (контракт-тест).
> **ADR:** —

---

## 1. Шкала брейкпоинтов (индустриальная, Tailwind)

Подход **mobile-first** (`min-width`). Значения зафиксированы как CSS-токены в
`./frontend/src/styles/tokens.css`:

| Токен | Значение | Класс |
|---|---|---|
| `--bp-sm` | `640px` | sm |
| `--bp-md` | `768px` | md |
| `--bp-lg` | `1024px` | lg |
| `--bp-xl` | `1280px` | xl |
| `--bp-2xl` | `1536px` | 2xl |

> CSS custom properties **не работают** в условии `@media` — в медиазапросах
> используются literal-значения, совпадающие со шкалой (`768px`, `1024px`, …).
> Off-scale числа (1100/960/900/860/720 и т.п.) не вводить; сводить к ближайшей
> ступени. Исключение — точечные микро-брейки скрытия столбцов таблиц (`480px`),
> для которых в шкале нет аналога.

## 2. Три класса ширины контента

| Токен | Значение | Назначение |
|---|---|---|
| `--content-reading` | `768px` | проза: KB-статья, новость-детейл (45–75 символов в строке) |
| `--content-standard` | `1280px` | большинство списков / страниц |
| `--content-wide` | `1600px` | плотные сетки и таблицы: staff, photos, files, admin |

`--layout-content-max` — алиас на `--content-standard` (обратная совместимость
со старым кодом).

## 3. Единый wrapper страницы (fluid-контейнер)

`.u-page-wrap` в `./frontend/src/styles/utilities.css`:

```css
.u-page-wrap {
  --u-page-wrap-max: var(--content-standard);
  width: min(100% - 2 * var(--page-gutter), var(--u-page-wrap-max));
  margin-inline: auto;
}
.u-page-wrap--reading { --u-page-wrap-max: var(--content-reading); }
.u-page-wrap--wide    { --u-page-wrap-max: var(--content-wide); }
```

- **fluid-gutter** `--page-gutter: clamp(16px, 4vw, 48px)` — поля растут с шириной
  вьюпорта; снимает обе крайности (узкая плавающая колонка ↔ растяжка край-в-край).
- Снимает «скачки» ширины между разделами: контент капается осознанным классом,
  а не хардкодом 1200/1280/1440.

### Какой класс для какой страницы

- **standard** (по умолчанию) — списки и большинство страниц: Home, News-list,
  KB-list, Links, NewsForm, профиль (own).
- **`--reading`** — проза: KB-статья, новость-детейл, профиль (view-mode).
- **`--wide`** — плотные сетки/таблицы: Staff, Photos, Files, Admin.

### Когда класс, а когда токен

- **Одноколоночные страницы** → класс `.u-page-wrap[--reading|--wide]` на корне.
- **Шелл-страницы** (grid/flex с сайдбаром: Photos, Files, PublicFolder) → не
  навешивать wrapper-класс (конфликт с flex/grid-механикой), а кап делать токеном:
  `max-width: var(--content-wide); margin-inline: auto;`.

## 4. Сетки — intrinsic responsive

Вместо ручных `repeat(N, …)` + `@media` для числа колонок:

```css
grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
```

Сетка сама добирает колонки по доступной ширине; число колонок естественно
ограничено шириной контейнера. Рекомендуемые `min`: карточки новостей/KB ≈ 320px,
staff-карточки ≈ 280px.

## 5. JS-брейкпоинты

`./frontend/src/composables/useBreakpoints.ts` синхронизирован со шкалой:

| Флаг | Условие |
|---|---|
| `isMobile` | `< md (768)` |
| `isTablet` | `md..lg (768–1024)` |
| `isWide` | `≥ xl (1280)` |
| `isDesktopXl` | `≥ 2xl (1536)` |

## 6. Контракт-тест

`./frontend/tests/unit/layout-tokens.spec.ts` читает `tokens.css` + `utilities.css`
и фиксирует шкалу, три класса ширины, fluid-gutter и контракт `.u-page-wrap`.
При изменении значений шкалы — обновлять тест синхронно.
