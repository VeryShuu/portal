# ТЗ: Управление модулем «Экскурс по порталу» (Onboarding Tour)

## 1. Контекст и текущее состояние

В системе уже реализован первичный экскурс по порталу — компонент `./frontend/src/components/OnboardingTour.vue`. Он автоматически запускается при первом входе пользователя в систему, если:

- в `localStorage` отсутствует ключ `portal-onboarding-done`;
- в `user.preferences.onboarding_completed` не выставлен флаг `true`.

Шаги тура (5 шт.) захардкожены в `computed steps` внутри компонента: «Новости», «База знаний», «Ссылки», «Закладки», «Профиль». Заголовки и описания берутся из i18n-ключей `onboarding.steps.*`.

Прохождение тура фиксируется:

- на бэкенде — в JSONB-поле `users.preferences` (см. `./backend/app/models/user.py:57`), флаг `onboarding_completed`. Изменяется через эндпоинт `PATCH /api/v1/users/me/preferences` (см. `./backend/app/api/users/users_me_service.py:77`);
- на фронтенде — через `localStorage` (быстрый кэш на клиенте).

**Проблема:** администратор не может через UI:

1. Глобально выключить экскурс (например, если в компании выкатили другой обучающий материал).
2. Принудительно сбросить статус прохождения у всех сотрудников (например, после крупного обновления интерфейса), чтобы все увидели тур заново.
3. Редактировать тексты шагов (опционально, см. п. 7).

## 2. Цели

1. Предоставить администратору централизованное управление модулем экскурса через раздел «Администрирование».
2. Сохранить совместимость с уже пройденным экскурсом у действующих пользователей (по умолчанию модуль включён, состояние не сбрасывается).
3. Соответствовать существующим архитектурным паттернам портала (system_config + admin endpoint + manage-drawer).

## 3. Backend

### 3.1. Расширение `SystemSettings`

Файл: `./backend/app/core/system_config.py`.

Добавить в `_SystemSettingsBase`, `SystemSettingsIn`, `SystemSettingsPatch`, `SystemSettingsOut` новые поля:

- `onboarding_enabled: bool = Field(default=True)` — глобальный флаг включения модуля экскурса.
- `onboarding_reset_trigger: str = Field(default="")` — ISO-8601 метка времени последнего «сброса» (как watermark для клиентского кеша). Пустая строка = сброса не было.

Поля будут автоматически попадать в `/data/settings/system.json` через существующую логику `_save_system_settings()` / `load_system_settings_shared()` и публиковаться в кэш Redis (через `bump_version`).

### 3.2. Эндпоинт сброса прохождения у всех пользователей

Файл: `./backend/app/api/system_settings.py`.

Добавить:

```
POST /api/v1/admin/system/settings/onboarding/reset
```

Поведение:

1. Требует `AdminDep` (как и остальные admin-эндпоинты).
2. SQL-обновление в одном запросе:
   ```sql
   UPDATE users
   SET preferences = preferences - 'onboarding_completed'
   WHERE preferences ? 'onboarding_completed';
   ```
   (использовать `jsonb -` операцию через SQLAlchemy `func.jsonb_set`/`text` — паттерн в существующих миграциях).
3. Обновить в `system.json` поле `onboarding_reset_trigger = utcnow().isoformat()`.
4. Вызвать `bump_version(redis, "system_settings")` и `bump_version(redis, "user_preferences")` (если есть инвалидатор для пользователей; иначе только settings).
5. Залогировать `admin.onboarding_reset` (структурированный лог с `admin_id` и количеством затронутых строк).
6. Ответ: `{"updated": <int>, "reset_trigger": "<iso8601>"}`.

### 3.3. Публичный канал чтения настроек экскурса

Эндпоинт `GET /api/v1/portal/gallery-links` уже отдаёт публичные настройки. По аналогии нужно либо:

- расширить существующий публичный эндпоинт настроек портала (если есть `GET /api/v1/settings` или аналог);
- либо ввести поля в `SystemSettingsPublicOut`, который возвращается анонимно/всем авторизованным пользователям.

Минимально достаточно отдавать публично только:

- `onboarding_enabled: bool`
- `onboarding_reset_trigger: str` (используется фронтом как «версия» для сравнения с локальным watermark).

Использовать существующий `RedisDep` + `load_system_settings_shared`.

### 3.4. Логика сброса на клиенте (комбинация backend + frontend)

Сервер не «трогает» localStorage клиента напрямую. Клиент сравнивает локально сохранённый `last_seen_reset_trigger` с пришедшим из API `onboarding_reset_trigger`:

- если значения различаются — локальный флаг `portal-onboarding-done` игнорируется (или удаляется), тур запускается заново;
- после успешного прохождения — клиент сохраняет новый watermark.

Для пользователей, у которых поле `onboarding_completed` сброшено через п. 3.2, серверный флаг `user.preferences.onboarding_completed` тоже отсутствует — тур стартует.

### 3.5. Тесты backend

Файл: `./backend/tests/api/test_system_settings.py` (или новый `test_onboarding_admin.py`).

Кейсы:

- `PATCH /admin/system/settings { onboarding_enabled: false }` — успех, поле сохранено, версия в Redis повышена.
- `POST /admin/system/settings/onboarding/reset` без admin — 403.
- `POST /admin/system/settings/onboarding/reset` — флаг удаляется у всех пользователей с `onboarding_completed=true`, поле `onboarding_reset_trigger` обновлено, версия в Redis повышена.
- `GET` публичного эндпоинта возвращает поля `onboarding_enabled` и `onboarding_reset_trigger`.

## 4. Frontend

### 4.1. Pinia-стор настроек системы

Использовать существующий стор системных настроек (если есть `useSystemSettingsStore`, иначе стор аналогичный `./frontend/src/stores/modules.ts`). Добавить getters:

- `onboardingEnabled: boolean` — из публичного эндпоинта настроек.
- `onboardingResetTrigger: string` — оттуда же.

### 4.2. Компонент `OnboardingModuleSettings.vue`

Файл: `./frontend/src/components/admin/OnboardingModuleSettings.vue`.

Стиль и структура — по аналогии с `./frontend/src/components/admin/PhotosModuleSettings.vue` и `./frontend/src/components/admin/MeetingsModuleSettings.vue`.

Содержимое:

1. **Секция «Общие»**:
   - `n-switch` v-model для `onboarding_enabled` (i18n: `admin.modules.onboarding.enabled`).
   - Кнопка `n-button type="primary"` «Сохранить» → `PATCH /api/v1/admin/system/settings`.

2. **Секция «Сброс прохождения»**:
   - Описание-подсказка.
   - Кнопка `n-button type="warning"` «Сбросить для всех пользователей» с `n-popconfirm` подтверждением → `POST /api/v1/admin/system/settings/onboarding/reset`.
   - После успеха — `n-message.success` с количеством затронутых пользователей.

3. **(Опционально) Секция «Шаги тура»** — см. п. 7.

### 4.3. Открытие drawer по URL-команде

В административной странице (`./frontend/src/pages/AdminPage.vue` или там, где находится модуль «О портале») использовать существующий `useManageDrawer` (`./frontend/src/composables/useManageDrawer.ts`):

```ts
const manage = useManageDrawer(['onboarding'])
```

Render:

```vue
<n-drawer :show="manage.is('onboarding')" :width="520" @update:show="(v) => !v && manage.close()">
  <n-drawer-content :title="t('admin.modules.onboarding.title')">
    <OnboardingModuleSettings />
  </n-drawer-content>
</n-drawer>
```

Открытие — через ссылку/кнопку в админ-панели: `router.push({ query: { manage: 'onboarding' } })` либо переход на `…?manage=onboarding`.

Async-импорт компонента:

```ts
const OnboardingModuleSettings = defineAsyncComponent(
  () => import('../../components/admin/OnboardingModuleSettings.vue'),
)
```

### 4.4. Интеграция в `OnboardingTour.vue`

Файл: `./frontend/src/components/OnboardingTour.vue`.

Изменения в `<script setup>`:

1. Импортировать стор системных настроек:
   ```ts
   import { useSystemSettingsStore } from '../stores/systemSettings'
   const systemSettings = useSystemSettingsStore()
   ```

2. В watch авто-запуска тура (`watch(() => auth.user, ...)`) учитывать:
   - `if (!systemSettings.onboardingEnabled) return` — модуль выключен глобально → тур не показывается.
   - Сравнение `localStorage.getItem(LS_RESET_KEY)` с `systemSettings.onboardingResetTrigger`:
     - если значения различаются → считать `lsDone = false`, сбросить локальный флаг.

3. Хранить новый ключ `LS_RESET_KEY = 'portal-onboarding-reset-trigger'`. Обновлять его в `finish()` после успешного сохранения.

4. Метод `startTour` (через `defineExpose`) оставить без изменений — администратор по-прежнему может запустить тур вручную (например, кнопкой «Посмотреть экскурс ещё раз» в пользовательском меню).

### 4.5. i18n

Добавить ключи в `./frontend/src/i18n/locales/ru.ts` (и `en.ts`, если есть):

- `admin.modules.onboarding.title` — «Экскурс по порталу»
- `admin.modules.onboarding.enabled` — «Показывать экскурсию новым пользователям»
- `admin.modules.onboarding.resetTitle` — «Сброс прохождения»
- `admin.modules.onboarding.resetDescription` — «При сбросе все сотрудники увидят экскурс заново при следующем входе.»
- `admin.modules.onboarding.resetButton` — «Сбросить для всех пользователей»
- `admin.modules.onboarding.resetConfirm` — «Сбросить флаг прохождения экскурса у всех пользователей?»
- `admin.modules.onboarding.resetSuccess` — «Сброшено для {count} пользователей»

### 4.6. Тесты frontend

- Unit-тест на `OnboardingTour.vue`: тур не стартует, если `onboardingEnabled = false`.
- Unit-тест на `OnboardingTour.vue`: при отличии `onboardingResetTrigger` от локального watermark тур запускается, даже если в `localStorage` был флаг.
- (Опционально) Playwright e2e в `./frontend/tests/`: открытие drawer по `?manage=onboarding`, переключение switch, нажатие «Сбросить».

## 5. Контракт API (сводно)

| Метод | Путь | Описание | Auth |
|-------|------|----------|------|
| `GET` | `/api/v1/admin/system/settings` | Чтение настроек (включает `onboarding_enabled`, `onboarding_reset_trigger`) | Admin |
| `PATCH` | `/api/v1/admin/system/settings` | Частичное обновление (включая `onboarding_enabled`) | Admin |
| `POST` | `/api/v1/admin/system/settings/onboarding/reset` | Сброс `onboarding_completed` у всех пользователей; обновляет `onboarding_reset_trigger` | Admin |
| `GET` | `/api/v1/portal/system/public` (или существующий публичный) | Возвращает `onboarding_enabled`, `onboarding_reset_trigger` для фронта | Public/Auth |

## 6. Миграции

Миграция БД не требуется — `users.preferences` уже JSONB. Изменения только в JSON-конфиге системы (`/data/settings/system.json`) и в коде.

## 7. Опционально: редактирование шагов экскурса через UI

Если требуется управление текстами шагов, расширение:

- В `SystemSettings` добавить поле:
  ```python
  onboarding_steps: list[OnboardingStep] | None = Field(default=None)
  ```
  где `OnboardingStep` — Pydantic-модель с полями `selector: str`, `title: str`, `body: str`, `order: int`.
- Если поле `None` — используется дефолтный набор (текущий захардкоженный список из `OnboardingTour.vue`, перенесённый в i18n).
- В админ-компоненте `OnboardingModuleSettings.vue` — таблица с inline-редактированием (`n-data-table` + `n-input`), кнопки «Добавить шаг», «Удалить», «Переместить вверх/вниз».
- В `OnboardingTour.vue` — `steps` берётся из стора, fallback на дефолтные значения.

В рамках первой итерации поле `onboarding_steps` **не реализуем**, оставляем как пункт развития (требует дополнительного UX-дизайна и согласования с переводчиками).

## 8. Чек-лист реализации

### Backend

- [ ] `./backend/app/core/system_config.py` — добавить поля `onboarding_enabled`, `onboarding_reset_trigger` в 4 модели.
- [ ] `./backend/app/api/system_settings.py` — endpoint `POST /admin/system/settings/onboarding/reset`.
- [ ] Расширить публичный endpoint (или создать) для выдачи `onboarding_enabled` + `onboarding_reset_trigger`.
- [ ] Тесты: `./backend/tests/api/test_onboarding_admin.py`.
- [ ] Обновить `./openapi.json` (через автогенерацию).

### Frontend

- [ ] Расширить стор системных настроек: getters `onboardingEnabled`, `onboardingResetTrigger`.
- [ ] `./frontend/src/components/admin/OnboardingModuleSettings.vue` — новый компонент (switch + reset).
- [ ] Подключить drawer `?manage=onboarding` в админ-странице.
- [ ] `./frontend/src/components/OnboardingTour.vue` — учёт `onboardingEnabled` и watermark `onboardingResetTrigger`.
- [ ] i18n-ключи `admin.modules.onboarding.*`.
- [ ] Unit-тесты для `OnboardingTour.vue`.

### Документация

- [ ] Обновить `./docs/api-contracts.md` записью про новый endpoint.
- [ ] Упомянуть в `./docs/adr.md` решение о хранении watermark вместо явной push-нотификации клиенту.

## 9. Риски и ограничения

- **Кэш Redis.** После сохранения настроек обязательно повышать версию (`bump_version(redis, "system_settings")`), иначе TTL 60 с может задержать применение.
- **Гонка при reset.** Если пользователь в момент сброса как раз сохраняет прохождение, его новая запись «победит» — повторный сброс администратором решит проблему.
- **localStorage.** Если у пользователя выставлен `portal-onboarding-done` и **выключен** глобальный флаг, мы НЕ показываем тур (правильное поведение). Если флаг включён, но `reset_trigger` совпадает — тур не показываем повторно.
- **SSE/инвалидация preferences.** При сбросе серверный `users.preferences` обновляется напрямую в БД — текущая сессия пользователя продолжит работать со старым значением до следующего `GET /me`. Это приемлемо, так как тур стартует именно «при следующем входе».
