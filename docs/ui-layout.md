# UI Layout — брейкпоинты и ширины контента

> **Когда читать:** вёрстка новой страницы/раздела, выбор ширины контента, адаптив под широкие экраны (1920×1080+), правка `@media`-запросов, добавление сеток.
> **Ключевой код:** `./frontend/src/styles/tokens.css` (шкала), `./frontend/src/styles/utilities.css` (`.u-page-wrap`), `./frontend/src/composables/useBreakpoints.ts` (JS-флаги), `./frontend/tests/unit/layout-tokens.spec.ts` (контракт-тест).
> **ADR:** —. **См. также:** —.

> Этот документ регламентирует единую шкалу брейкпоинтов и классов ширины контента для фронтенд-приложения на Vue 3. Он описывает принципы создания адаптивных страниц с использованием CSS-переменных, флюидных отступов и медиазапросов, а также предоставляет JS-интерфейс для адаптивной логики в компонентах.

---

## 1. Обзор

| Аспект | Значение |
|---|---|
| Стек вёрстки | CSS Custom Properties (Design Tokens), Flexbox, CSS Grid (intrinsic responsive) |
| Системные файлы | `./frontend/src/styles/tokens.css`, `./frontend/src/styles/utilities.css` |
| JS-интерфейс | Vue Composables (`./frontend/src/composables/useBreakpoints.ts`) |
| Тесты | Vitest (`./frontend/tests/unit/layout-tokens.spec.ts`) |

---

## 2. Структура кода

| Слой | Путь | Назначение |
|---|---|---|
| Стили | `./frontend/src/styles/tokens.css` | Базовые дизайн-токены (цвета, шрифты, брейкпоинты) |
| Стили | `./frontend/src/styles/utilities.css` | Утилитарные классы вёрстки и класс `.u-page-wrap` |
| Слой логики | `./frontend/src/composables/useBreakpoints.ts` | Composable-функция для реактивного определения брейкпоинтов |
| Тесты | `./frontend/tests/unit/layout-tokens.spec.ts` | Контрактный unit-тест для CSS-переменных и классов |

---

## 3. Модель данных

Не применимо (компонент вёрстки фронтенда).

---

## 4. Модель прав (ACL)

Не применимо.

---

## 5. REST API

Не применимо.

---

## 6. Шкала брейкпоинтов (индустриальная, Tailwind)

Подход **mobile-first** (`min-width`). Значения зафиксированы как CSS-токены в `./frontend/src/styles/tokens.css`:

| Токен | Значение | Класс |
|---|---|---|
| `--bp-sm` | `640px` | sm |
| `--bp-md` | `768px` | md |
| `--bp-lg` | `1024px` | lg |
| `--bp-xl` | `1280px` | xl |
| `--bp-2xl` | `1536px` | 2xl |

> CSS custom properties **не работают** в условии `@media` — в медиазапросах используются literal-значения, совпадающие со шкалой (`768px`, `1024px`, …). Off-scale числа (1100/960/900/860/720 и т.п.) не вводить; сводить к ближайшей ступени. Исключение — точечные микро-брейки скрытия столбцов таблиц (`480px`), для которых в шкале нет аналога.

---

## 7. Три класса ширины контента и Wrapper

| Токен | Значение | Назначение |
|---|---|---|
| `--content-reading` | `768px` | проза: KB-статья, новость-детейл (45–75 символов в строке) |
| `--content-standard` | `1280px` | большинство списков / страниц |
| `--content-wide` | `1600px` | плотные сетки и таблицы: staff, photos, files, admin |

`--layout-content-max` — алиас на `--content-standard` (обратная совместимость со старым кодом).

### Единый wrapper страницы (fluid-контейнер)

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

- **fluid-gutter** `--page-gutter: clamp(16px, 4vw, 48px)` — поля растут с шириной вьюпорта; снимает обе крайности (узкая плавающая колонка ↔ растяжка край-в-край).
- Снимает «скачки» ширины между разделами: контент капается осознанным классом, а не хардкодом 1200/1280/1440.

### Какой класс для какой страницы

- **standard** (по умолчанию) — списки и большинство страниц: Home, News-list, KB-list, Links, NewsForm, профиль (own).
- **`--reading`** — проза: KB-статья, новость-детейл, профиль (view-mode).
- **`--wide`** — плотные сетки/таблицы: Staff, Photos, Files, Admin.

### Когда класс, а когда токен

- **Одноколоночные страницы** → класс `.u-page-wrap[--reading|--wide]` на корне.
- **Шелл-страницы** (grid/flex с сайдбаром: Photos, Files, PublicFolder) → не навешивать wrapper-класс (конфликт с flex/grid-механикой), а кап делать токеном: `max-width: var(--content-wide); margin-inline: auto;`.

---

## 8. Сетки — intrinsic responsive

Вместо ручных `repeat(N, …)` + `@media` для числа колонок:

```css
grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
```

Сетка сама добирает колонки по доступной ширине; число колонок естественно ограничено шириной контейнера. Рекомендуемые `min`: карточки новостей/KB ≈ 320px, staff-карточки ≈ 280px.

---

## 9. JS-брейкпоинты

`./frontend/src/composables/useBreakpoints.ts` синхронизирован со шкалой:

| Флаг | Условие |
|---|---|
| `isMobile` | `< md (768)` |
| `isTablet` | `md..lg (768–1024)` |
| `isWide` | `≥ xl (1280)` |
| `isDesktopXl` | `≥ 2xl (1536)` |

---

## Безопасность

Для предотвращения XSS-уязвимостей при динамической стилизации через JS избегайте ручного конструирования inline-стилей из пользовательского ввода. Всегда используйте безопасные CSS-переменные и предписанные утилитарные классы.

---

## События аудита

Не применимо (события аудита фиксируются только на бэкенде).

---

## Тесты

| Тип | Путь | Покрывает |
|---|---|---|
| Unit | `./frontend/tests/unit/layout-tokens.spec.ts` | Читает `./frontend/src/styles/tokens.css` и `./frontend/src/styles/utilities.css` и фиксирует шкалу брейкпоинтов, классы ширины контента, fluid-gutter и контракт класса `.u-page-wrap` |

---

## Связанные документы

- `./docs/_TEMPLATE.md`
- `./docs/ui-layout.md` (этот документ)
