# Модуль «Экскурс по порталу» (Onboarding Tour)

Краткий пошаговый тур по основным разделам портала. Запускается автоматически при первом входе пользователя; администратор может включать/выключать модуль, редактировать шаги, помечать новые пункты как «новинку» и сбрасывать прохождение у всех сотрудников.

---

## 1. Назначение и сценарии

| Сценарий | Что происходит |
|---|---|
| Первый вход нового сотрудника | Если модуль включён и есть шаги — через ~0.8 с после загрузки запускается полный экскурс. |
| Повторный вход того же пользователя | Тур не показывается (зафиксирован флаг `onboarding_completed`). |
| Администратор нажал «Сбросить для всех пользователей» | У всех в БД удаляется флаг `onboarding_completed`, обновляется `onboarding_reset_trigger`. При следующем входе тур запускается заново. |
| Добавили новый пункт меню → отметили шаг `is_new=true` | Пользователи, уже прошедшие основной тур, увидят мини-тур только из новых шагов. |
| Пользователь хочет посмотреть тур ещё раз | Меню пользователя → «Посмотреть экскурс заново». |
| Модуль выключен глобально | Тур никогда не стартует автоматически (ручной запуск из меню по-прежнему работает). |

---

## 2. Хранилище состояния

### 2.1. Глобальные настройки модуля

Файл `/data/settings/system.json` (модель `./backend/app/core/system_config.py:SystemSettings`):

| Поле | Тип | Назначение |
|---|---|---|
| `onboarding_enabled` | `bool` (default `true`) | Глобальный switch модуля. |
| `onboarding_reset_trigger` | `str` (ISO-8601, default `""`) | Watermark последнего «сброса для всех». Клиент сравнивает с локально сохранённым значением, чтобы понять, нужно ли проигнорировать локальный кэш. |
| `onboarding_steps` | `list[OnboardingStep] \| null` | Переопределённый набор шагов. `null` ⇒ используются дефолтные шаги из i18n. |

### 2.2. `OnboardingStep`

```python
class OnboardingStep(BaseModel):
    id: str        = Field(default="", max_length=64)   # [A-Za-z0-9_-]+
    selector: str  = Field(min_length=1, max_length=500)
    title: str     = Field(min_length=1, max_length=200)
    body: str      = Field(default="", max_length=2000)
    is_new: bool   = Field(default=False)
```

- `id` — стабильный идентификатор шага. Пустое/повторяющееся значение бэкенд автозаполняет 12-символьным hex (`uuid4().hex[:12]`).
- `selector` — CSS-селектор подсвечиваемого элемента. UI предлагает выпадающий список из 15 готовых таргетов (`./frontend/src/utils/tourTargets.ts`); можно ввести любой произвольный селектор. Большинство дефолтных селекторов используют CSS `:has()` (Chrome 105+, Safari 15.4+, Firefox 121+).
- `is_new` — пометка «новинка». Шаги с `is_new=true` показываются как мини-тур пользователям, прошедшим основной экскурс и ещё не видевшим данный `id`.

### 2.3. Пользовательские предпочтения

`users.preferences` (JSONB, см. `./backend/app/models/user.py`):

| Ключ | Тип | Назначение |
|---|---|---|
| `onboarding_completed` | `bool` | Пользователь прошёл основной тур. |
| `onboarding_seen_step_ids` | `list[str]` (cap 500–1000) | Список `id` шагов, которые пользователь уже видел. Используется для дельта-режима (`is_new`). |

### 2.4. localStorage клиента

| Ключ | Назначение |
|---|---|
| `portal-onboarding-done` | Быстрый кэш «тур пройден» для немедленной проверки до прихода `/users/me`. |
| `portal-onboarding-reset-trigger` | Локальная копия `onboarding_reset_trigger`. Если расходится с серверной — локальный флаг игнорируется. |

---

## 3. Backend API

| Метод | Путь | Auth | Описание |
|---|---|---|---|
| `GET` | `/api/v1/admin/system/settings` | Admin | Полные системные настройки (включая поля онбординга). |
| `PATCH` | `/api/v1/admin/system/settings` | Admin | Частичное обновление. `onboarding_reset_trigger` через PATCH не принимается (управляется только эндпоинтом reset). `onboarding_steps`: омитим ⇒ оставить как есть; `null` ⇒ удалить override; массив ⇒ заменить. |
| `POST` | `/api/v1/admin/system/settings/onboarding/reset` | Admin | Удаляет ключ `onboarding_completed` у всех пользователей, обновляет watermark `onboarding_reset_trigger`. Ответ: `{updated: int, reset_trigger: str}`. Audit-event: `system_settings.onboarding_reset`. |
| `POST` | `/api/v1/admin/system/settings/onboarding/steps/reset-views` | Admin | Body: `{step_id: str}`. Удаляет `step_id` из массива `onboarding_seen_step_ids` у всех пользователей. Ответ: `{updated: int, step_id: str}`. Audit-event: `system_settings.onboarding_step_reset_views`. |
| `GET` | `/api/v1/portal/onboarding` | Public/Auth | Публичный канал чтения для фронта: `{onboarding_enabled, onboarding_reset_trigger, onboarding_steps}`. |
| `PATCH` | `/api/v1/users/me/preferences` | User | Поля `onboarding_completed: bool` и `onboarding_seen_step_ids: list[str]` (max 1000, серверный cap 500). |

### 3.1. SQL: «Сброс прохождения»

```sql
UPDATE users
   SET preferences = preferences - 'onboarding_completed'
 WHERE preferences ? 'onboarding_completed';
```

### 3.2. SQL: «Сброс просмотров шага»

```sql
UPDATE users
   SET preferences = jsonb_set(
         preferences,
         '{onboarding_seen_step_ids}',
         (preferences->'onboarding_seen_step_ids') - :sid
       )
 WHERE jsonb_typeof(preferences->'onboarding_seen_step_ids') = 'array'
   AND preferences->'onboarding_seen_step_ids' ? :sid;
```

### 3.3. Кэш и инвалидация

- Системные настройки кэшируются в Redis под ключом `system_settings` (TTL 60 с) — см. `./backend/app/core/system_config.py:load_system_settings_shared`.
- После любого PATCH/POST вызывается `bump_version(redis, "system_settings")`, что инвалидирует кэш на всех инстансах.

---

## 4. Frontend

### 4.1. Pinia-стор `./frontend/src/stores/onboarding.ts`

```ts
useOnboardingSettingsStore()
  .load()                 // GET /portal/onboarding
  .setSettings(partial)   // локальное обновление (после успешного PATCH в админке)

// getters
.onboardingEnabled       // bool
.onboardingResetTrigger  // str
.onboardingSteps         // OnboardingStep[]  (fallback на defaultOnboardingSteps())
.hasCustomSteps          // bool
```

Дефолтные шаги (`defaultOnboardingSteps()`): `default-news`, `default-kb`, `default-links`, `default-profile`.

### 4.2. Плеер тура `./frontend/src/components/OnboardingTour.vue`

Монтируется один раз в `./frontend/src/components/AppLayout.vue` через `<OnboardingTour ref="tourRef" />`. Экспонирует:

```ts
{
  startTour(): void              // полный тур по всем шагам
  startDeltaTour(ids: string[])  // мини-тур только по указанным id
}
```

Логика авто-старта (`maybeAutoStart`):

```
если user изменился (по user.id):
  если модуль выключен ИЛИ шагов нет → return
  если триггер сброса разошёлся → localStorage.removeItem('portal-onboarding-done')
  если !lsDone && !prefsDone → запустить полный тур
  иначе:
     newSteps = шаги c is_new=true, id ∉ user.preferences.onboarding_seen_step_ids
     если newSteps непустой → startDeltaTour(newSteps.map(id))
```

На завершение (`finish()`):
- собирает `mergedSeen` = (prevSeen ∪ shownIds) ∩ allKnownIds, обрезает до 500;
- `PATCH /users/me/preferences` с `{onboarding_seen_step_ids, [onboarding_completed: true в полном режиме]}`;
- в полном режиме также пишет `localStorage` (`portal-onboarding-done` + `portal-onboarding-reset-trigger`).

Прочее:
- Клик по backdrop **не** закрывает тур — только явные кнопки `Skip`/`Next`/`Finish`.
- Попап позиционируется на `resize`/`scroll` (passive-listeners, очистка в `onBeforeUnmount`).
- При смене пользователя (logout/login в одной сессии) `autoStartedFor` сбрасывается.

### 4.3. Админ-компонент `./frontend/src/components/admin/OnboardingModuleSettings.vue`

Открывается как drawer по URL `?manage=onboarding` со страницы Администрирование → Модули. Состоит из трёх секций:

1. **Общие** — switch `onboarding_enabled` + кнопка «Сохранить» (PATCH).
2. **Шаги экскурса** — список шагов с inline-редакторами:
   - бейдж `#N · {id}`;
   - кнопки ↑/↓/✕;
   - селектор: `n-select` с группами (готовые таргеты из `./frontend/src/utils/tourTargets.ts`) + произвольный ввод;
   - заголовок, описание (textarea, autosize 2–5);
   - чекбокс `is_new` + popconfirm «Сбросить просмотры»;
   - подсказка о требованиях к браузеру, если селектор содержит `:has(`.
   - кнопки «Добавить шаг», «Отмена» (отключена без изменений), «Вернуть шаги по умолчанию», «Сохранить» (отключена без изменений).
   - Dirty-state защищает форму от перезаписи при инвалидации query.
3. **Сброс прохождения** — popconfirm + кнопка warning, показывает «Последний сброс: {date}».

### 4.4. Точка входа «Посмотреть экскурс заново»

Пункт меню пользователя (`./frontend/src/components/layout/HeaderUserMenu.vue`) с ключом `replay-tour`, вызывает `tourRef.startTour()` через prop `onAbout` из `./frontend/src/components/AppLayout.vue`.

### 4.5. i18n

Все ключи — `admin.modules.onboarding.*` в `./frontend/src/i18n/ru.json` и `./frontend/src/i18n/en.json`. Шаги по умолчанию используют `onboarding.steps.{news,kb,links,profile}.{title,body}`.

---

## 5. Операционные процедуры

### 5.1. Включить/выключить экскурс

Администрирование → Модули → блок «Экскурс по порталу» → switch.
Либо через быстрый switch в карточке модуля, либо в drawer-е «Открыть настройки →».

### 5.2. Сбросить прохождение для всех

Drawer «Экскурс по порталу» → секция «Сброс прохождения» → «Сбросить для всех пользователей». Используйте после крупного UI-обновления, когда есть смысл, чтобы все увидели тур заново.

### 5.3. Добавить новый шаг

1. Drawer → «Шаги экскурса» → «+ Добавить шаг».
2. Выберите элемент в выпадающем списке или введите CSS-селектор вручную.
3. Заполните заголовок и описание.
4. (опционально) Включите «Показать как новинку», чтобы шаг был показан уже прошедшим тур.
5. «Сохранить». `id` будет автогенерирован.

### 5.4. Подсветить новый пункт меню как «новинку»

1. Добавьте `data-tour-id` на новый пункт меню (см. `./frontend/src/composables/useAppMenu.ts:renderNavLabel`).
2. Если нужно — добавьте таргет в `./frontend/src/utils/tourTargets.ts`.
3. В админке создайте/отредактируйте шаг, выберите таргет, поставьте `is_new=true`, сохраните.
4. Все, кто уже прошёл основной тур, при следующем входе увидят мини-подсказку. После просмотра `id` попадёт в их `onboarding_seen_step_ids` и повторно не покажется.
5. Когда новинка перестанет быть актуальной — снимите галочку `is_new` (либо удалите шаг).

### 5.5. Перепоказать конкретный «новый» шаг

Шаг в админке → «Сбросить просмотры». Удалит `id` шага из `onboarding_seen_step_ids` у всех пользователей; следующая загрузка покажет мини-подсказку заново.

### 5.6. Удалить override и вернуть дефолтные шаги

«Вернуть шаги по умолчанию» → confirm. PATCH с `onboarding_steps: null`.

---

## 6. Тесты

### 6.1. Backend

`./backend/tests/unit/test_system_settings.py::TestOnboardingSettings`:

- `test_defaults`, `test_to_out_includes_onboarding`, `test_patch_onboarding_enabled`;
- `test_public_endpoint_returns_fields`, `test_public_endpoint_returns_steps`;
- `test_reset_requires_admin`, `test_reset_updates_trigger_and_returns_count`;
- `test_onboarding_steps_default_is_none`, `test_onboarding_step_validation`;
- `test_step_id_autofill`;
- `test_reset_step_views_requires_admin`, `test_reset_step_views_returns_count`;
- `test_patch_distinguishes_omitted_vs_explicit_steps`.

Запуск: `cd backend && pytest tests/unit/test_system_settings.py -q`.

### 6.2. Frontend

`vue-tsc --noEmit` — типы. Ручное тестирование сценариев из §1 через Playwright/UI.

---

## 7. Риски и ограничения

- **Кэш Redis.** TTL 60 с; после PATCH автоматически вызывается `bump_version`.
- **Гонка при reset.** Если пользователь в момент глобального сброса как раз сохраняет прохождение, его запись «победит» — повторный сброс решит проблему.
- **localStorage.** Игнорируется, если расходится watermark `onboarding_reset_trigger`. Очищается клиентом при детекте расхождения.
- **SSE/инвалидация preferences.** При `reset` БД обновляется напрямую — текущая сессия пользователя видит старое значение до следующего `GET /users/me`. Тур стартует именно «при следующем входе/перезагрузке».
- **CSS `:has()`.** Дефолтные селекторы зависят от `:has()`. Для устаревших браузеров вводите альтернативный селектор (например, `[data-tour-id="..."]` без обёртки).
- **Cap `onboarding_seen_step_ids`.** Клиент режет до 500, серверный валидатор — до 1000, сервис — до 500 (защита от раздутого JSONB).
- **Orphan-ids.** При сохранении прогресса фильтруются по актуальному `onboardingSteps` — удалённые шаги автоматически выпадают из массива.

---

## 8. Связанные файлы

**Backend**
- `./backend/app/core/system_config.py` — модели + persistence.
- `./backend/app/api/system_settings.py` — admin/public эндпоинты, `_ensure_step_ids`.
- `./backend/app/schemas/user.py` — `PatchPreferencesRequest`.
- `./backend/app/api/users/users_me_service.py:patch_my_preferences` — мердж preferences + cap.
- `./backend/tests/unit/test_system_settings.py` — `TestOnboardingSettings`.

**Frontend**
- `./frontend/src/stores/onboarding.ts` — Pinia-стор + дефолтные шаги.
- `./frontend/src/components/OnboardingTour.vue` — плеер тура.
- `./frontend/src/components/admin/OnboardingModuleSettings.vue` — admin drawer.
- `./frontend/src/components/AppLayout.vue` — монтирование `<OnboardingTour>` и проброс `startTour`.
- `./frontend/src/components/layout/HeaderUserMenu.vue` — пункт «Посмотреть экскурс заново».
- `./frontend/src/pages/admin/tabs/ModulesTab.vue` — карточка модуля + drawer.
- `./frontend/src/utils/tourTargets.ts` — каталог известных селекторов.
- `./frontend/src/i18n/ru.json`, `./frontend/src/i18n/en.json` — `admin.modules.onboarding.*`.
