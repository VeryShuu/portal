# Главная страница и виджеты

> **Когда читать:** структура главной страницы, настройка виджетов, интеграция с внешними API, мировое время и погода.
> **Ключевой код:** `./frontend/src/pages/HomePage.vue`, `./frontend/src/components/HeroBlock.vue`, `./frontend/src/components/widgets/WorldClockWidget.vue`, `./frontend/src/components/widgets/MeetingsWidget.vue`, `./frontend/src/components/widgets/PhotosWidget.vue`.
> **ADR:** 038. **См. также:** `./docs/adr.md`, `./docs/news.md`, `./docs/meetings.md`, `./docs/photos.md`, `./docs/links-bookmarks.md`, `./docs/branding.md`.

> Главная страница интранет-портала представляет собой дашборд-лендинг, который агрегирует информацию из различных модулей (новости, встречи, фотогалерея) и содержит виджеты для повседневной работы. Этот функционал является преимущественно фронтенд-ориентированным: у главной страницы нет выделенного бэкенд-роутера, а виджеты используют API соответствующих модулей. Виджет «Время в городах» работает напрямую с внешним сервисом Open-Meteo со стороны клиента, без участия бэкенда портала.

---

## 1. Обзор

| Аспект | Значение |
|---|---|
| Backend | Отсутствует (данные запрашиваются из API других модулей) |
| Frontend | Vue 3 + Pinia + Naive UI (`./frontend/src/pages/HomePage.vue`, `./frontend/src/components/widgets/`) |
| Воркер | Отсутствует |
| Хранилище | `localStorage` (ключ `portal.worldClockCities.v2` для настроек городов, `portal.worldClockWeather.v1` для кэша погоды) |
| Префикс API | Отсутствует (внешние запросы к Open-Meteo) |
| ACL-кэш | Отсутствует |
| Источники данных | REST API модулей портала, внешний API Open-Meteo |
| Управление виджетом часов | `./frontend/src/pages/admin/tabs/WorldClockTab.vue` через drawer (доступно только Admin) |

---

## 2. Структура кода

| Слой | Путь | Назначение |
|---|---|---|
| Frontend Page | `./frontend/src/pages/HomePage.vue` | Главная страница портала; корень содержит стабильный `data-monitoring-ready="home"` для read-only synthetic-проверки |
| Component | `./frontend/src/components/HeroBlock.vue` | Приветственный блок с датой и временем суток |
| Component | `./frontend/src/components/widgets/PortalBanner.vue` | Портальный баннер в самом верху страницы |
| Component | `./frontend/src/components/widgets/HomeFeaturedNewsSection.vue` | Блок закрепленных новостей (Featured) |
| Component | `./frontend/src/components/widgets/HomeNewsGrid.vue` | Сетка обычных опубликованных новостей |
| Component | `./frontend/src/components/widgets/QuickServicesWidget.vue` | Виджет быстрых ссылок на популярные сервисы |
| Component | `./frontend/src/components/widgets/WorldClockWidget.vue` | Виджет мирового времени городов с погодой |
| Component | `./frontend/src/components/widgets/MeetingsWidget.vue` | Виджет ближайших бронирований переговорных |
| Component | `./frontend/src/components/widgets/PhotosWidget.vue` | Виджет свежих обработанных фотографий |
| Component | `./frontend/src/pages/admin/tabs/WorldClockTab.vue` | Настройка списка городов в административной панели |
| Composable | `./frontend/src/composables/useWorldClockCities.ts` | Управление списком городов в `localStorage` |
| Composable | `./frontend/src/composables/useWorldClockWeather.ts` | Запрос погоды Open-Meteo и кэширование в `localStorage` |
| Composable | `./frontend/src/composables/useWorldClockClock.ts` | Утилитарный таймер/время часов |
| Composable | `./frontend/src/composables/useManageDrawer.ts` | Управление открытием/закрытием drawer-панелей |
| Store | `./frontend/src/stores/links.ts` | Pinia-стор быстрых сервисов/ссылок |
| Store | `./frontend/src/stores/photos.ts` | Pinia-стор фотогалереи (SSE-интеграция) |
| Query | `./frontend/src/queries/meetings.ts` | Запросы бронирований переговорных |

---

## 3. Модель данных

Модуль не имеет собственных таблиц в базе данных. Данные о настройках городов и кэше погоды сохраняются локально на клиенте в `localStorage`:

- **Список городов** (`portal.worldClockCities.v2`): массив объектов `ClockCity`, содержащих поля `id`, `name`, `code`, `timezone`, `lat`, `lon`. При отсутствии записей загружается дефолтный список.
- **Кэш погоды** (`portal.worldClockWeather.v1`): словарь, где ключом является пара координат вида `lat|lon`, а значением — объект `WeatherSample` с полями `temperature` (число), `code` (код WMO) и `fetchedAt` (timestamp в миллисекундах).

---

## 4. Модель прав (ACL)

- **Обычные пользователи**:
  - Просмотр главной страницы и всех виджетов боковой панели.
  - Кастомизация списка городов отключена (используется общий или локальный дефолтный список).
- **Администраторы (Role: Admin)**:
  - Доступ к кнопке настроек (шестеренке) в виджете «Мировое время».
  - Полный доступ к панели управления списком городов (`./frontend/src/pages/admin/tabs/WorldClockTab.vue`).
  - Возможность выполнения CRUD-операций над городами, сортировки, сброса к дефолтным значениям.

---

## 5. REST API

Модуль не предоставляет собственных REST API-эндпоинтов на бэкенде. Для работы используются:
- API других модулей (новости, встречи, фотогалерея, база знаний).
- Внешний REST API **Open-Meteo** для получения текущей погоды:
  - URL: `https://api.open-meteo.com/v1/forecast?latitude=...&longitude=...&current=temperature_2m,weather_code&timezone=auto`
  - Используется бесшовный батч-запрос для всех городов списка одновременно.

---

## 6. Состав главной страницы

Интерфейс главной страницы (`./frontend/src/pages/HomePage.vue`) делится на следующие основные блоки:

- **Портальный баннер** — информационное сообщение в самом верху страницы. Показывается, если включен в настройках брендинга (`branding.isBannerActive`) и не был скрыт пользователем. Ключ скрытия сохраняется в `sessionStorage` под именем `home_banner_dismissed`.
- **Приветственный блок** (`./frontend/src/components/HeroBlock.vue`) — динамическое приветствие по времени суток, имя пользователя (из `./frontend/src/stores/auth.ts`), текущая дата на выбранном языке (RU/EN). После редизайна главной также включает: фоны по времени суток (слоты `hero-bg-morning/day/evening` с focal-point/zoom), подзаголовки по режиму `hero_subtitle_mode` (`auto`/`custom`/`hidden`, до 4 кастомных текстов) и часы мирового времени (`./frontend/src/components/widgets/HeroWorldClock.vue` — данные тех же composables, что и прежний WorldClockWidget).
- **Закрепленные новости** (Featured) — блок во всю ширину, выводящий pinned-новости. Карточки рендерятся через `./frontend/src/components/news/NewsCard.vue`, при загрузке используется скелетон `./frontend/src/components/SkeletonCard.vue`.
- **Основная колонка** — сетка новостей, где отображаются обычные опубликованные новости. Если новостей нет, показывается `./frontend/src/components/EmptyState.vue`. Дополнительно в основной колонке: полоса дней рождения (`./frontend/src/components/widgets/BirthdaysWidget.vue`).
- **Боковая колонка (aside)** — содержит набор функциональных виджетов.

---

## 7. Функционирование виджетов боковой панели

Боковая панель включает в себя следующие виджеты:

### Быстрые сервисы (QuickServicesWidget)
- **Что показывает**: Сетка из 8 сервисов (4×2) с их иконками или первыми буквами названий.
- **Источник данных**: Pinia-стор `./frontend/src/stores/links.ts`; выборка ссылок с флагом `show_on_home`, срез первых 8 (`./frontend/src/pages/composables/useHomeLinksPreview.ts`).
- **Управление**: Ссылки открываются через метод `linksStore.openLink(link)`. Переход ко всем ссылкам осуществляется по кнопке «Все» на страницу `/links`.

### Мировое время
- Часы перенесены в Hero-блок главной (`HeroWorldClock` внутри `./frontend/src/components/HeroBlock.vue`); отдельный `WorldClockWidget.vue` в боковой панели больше не используется. Данные и admin-настройка — прежние (см. §8).

### Закладки (QuickLinksWidget)
- `./frontend/src/components/widgets/QuickLinksWidget.vue` — персональные закладки пользователя в боковой панели.

### Ближайшие встречи (MeetingsWidget)
- **Что показывает**: До 5 ближайших бронирований переговорных текущего пользователя.
- **Источник данных**: Запрос `./frontend/src/queries/meetings.ts` (`useMyMeetingBookingsQuery`) с ограничением `limit: 5`. Отображается только если модуль `meetings` активен (`modulesStore.isEnabled('meetings')`).
- **Обновление**: Слушает глобальное событие `window` `'meetings:changed'` для автоматической инвалидации кэша запросов.

### Свежие фото (PhotosWidget)
- **Что показывает**: До `widget_limit` (по умолчанию 8) фотографий — последних добавленных (`widget_mode: recent`) или случайных (`widget_mode: random`; настройка модуля фото, см. `./docs/photos.md` §9).
- **Источник данных**: Pinia-стор фотогалереи `./frontend/src/stores/photos.ts`. Отображается только если модуль фото сконфигурирован.
- **Обновление**: Интегрировано с SSE. Метод `store.installRealtime()` подписывается на событие `'photos:processed'` и обновляет ленту с дебаунсом 500 мс.

---

## 8. Виджет «Время в городах» и внешняя интеграция

Работа виджета построена целиком на клиентской логике согласно ADR-038.

### Описание и хранение данных
- **Список городов**: Хранится локально в браузере пользователя в `localStorage` по ключу `portal.worldClockCities.v2`. При отсутствии пользовательских настроек загружается дефолтный список (Москва, Владивосток, Сахалин, Пусан).
- **Дефолтные города**:
  - Москва (`Europe/Moscow`, MSK)
  - Владивосток (`Asia/Vladivostok`, VVO)
  - Сахалин (`Asia/Sakhalin`, SAH)
  - Пусан (`Asia/Seoul`, PUS, таймзона Южной Кореи)

### Получение погоды (Open-Meteo)
- Погода запрашивается батч-запросом по координатам (`lat`/`lon`) всех городов одним сетевым запросом к бесплатному API: `https://api.open-meteo.com/v1/forecast?latitude=...&longitude=...&current=temperature_2m,weather_code&timezone=auto`.
- Позволяет избежать использования приватных API-ключей на фронтенде и дополнительной прокси-настройки на бэкенде.
- **Кэширование**: Результаты сохраняются в `localStorage` по ключу `portal.worldClockWeather.v1`. Время жизни кэша (`REFRESH_MS`) составляет **30 минут**.
- **Отказоустойчивость**: Любые сетевые сбои (оффлайн, таймауты, блокировка CORS) обрабатываются молча. В случае ошибки виджет просто убирает температуру и переключается на стандартную иконку солнца/луны (в зависимости от времени суток в таймзоне города) без вывода ошибок на экран.
- **Интеграция CSP**: Домены `https://api.open-meteo.com` и `https://geocoding-api.open-meteo.com` явно добавлены в разрешенный список директивы `connect-src` в конфигурационном скрипте `./nginx/render-config.sh`.

---

## 9. Особенности и нюансы

- **Синхронизация времени**: Обновление времени на часах виджета происходит каждые 30 секунд по таймеру в `./frontend/src/components/widgets/WorldClockWidget.vue`.
- **Определение времени суток и выходных**: Ночной режим (`clock-cube--night`) применяется, если локальный час в целевой зоне `< 7` или `>= 21`. Выходной режим (`clock-cube--weekend`) применяется, если день недели равен субботе (`Sat`) или воскресенью (`Sun`).
- **Разметка сетки**: Сетка виджета адаптивно меняет количество колонок: 1 колонка, если в списке 1 город, и 2 колонки, если городов 2 и более.
- **Дебаунс при обновлении по SSE**: Виджет недавних фото использует подписку на события реального времени с дебаунсом 500 мс для предотвращения избыточных сетевых запросов при пакетной загрузке фотографий.
- **Локализация (i18n)**: Язык отображения дней недели в HeroBlock и дат встреч автоматически переключается между RU/EN на основе текущей локали приложения.

---

## Безопасность

- **Отсутствие приватных ключей**: Использование бесплатного API Open-Meteo устраняет необходимость хранения секретных токенов и ключей на стороне фронтенда.
- **Интеграция CSP (Content Security Policy)**: Домены внешних API добавлены в белый список `connect-src` в `./nginx/render-config.sh` для предотвращения CORS и CSP блокировок в продакшене.
- **Изоляция административных функций**: Все методы модификации списка городов доступны исключительно пользователям с ролью Admin.

---

## События аудита

- Модуль является чисто фронтенд-ориентированным и не отправляет напрямую события аудита на бэкенд.

---

## Тесты

| Тип | Путь | Покрывает |
|---|---|---|
| Frontend Unit | `./frontend/tests/unit/home-page.spec.ts` | Рендеринг главной страницы, monitoring marker, заглушки виджетов и интеграция со сторами |
| Frontend Unit | `./frontend/tests/unit/world-clock-cities.spec.ts` | Логика composable `useWorldClockCities`: валидация, CRUD-операции, сброс и сортировка городов |

---

## Связанные документы

- `./docs/adr.md` — Философия архитектурных решений (ADR-038)
- `./docs/news.md` — Модуль новостей (интеграция в HomePage)
- `./docs/meetings.md` — Бронирование встреч (интеграция MeetingsWidget)
- `./docs/photos.md` — Фотогалерея (интеграция PhotosWidget)
- `./docs/links-bookmarks.md` — База ссылок (интеграция QuickServicesWidget)
- `./docs/branding.md` — Кастомизация брендинга и логотипов
