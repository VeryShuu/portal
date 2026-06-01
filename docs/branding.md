# Модуль «Брендинг» (Оформление портала)

> **Когда читать:** кастомизация внешнего вида портала, изменение логотипа, favicon, фонового изображения входа, настройка SMTP/Email.
> **Ключевой код:** `./backend/app/api/branding.py`, `./backend/app/schemas/branding.py`, `./frontend/src/stores/branding.ts`, `./frontend/src/pages/admin/tabs/BrandingTab.vue`, `./frontend/src/pages/admin/tabs/EmailTab.vue`.
> **ADR:** ADR-037.

---

## 1. Обзор

| Аспект | Значение |
|---|---|
| Backend | FastAPI (`./backend/app/api/branding.py`), JSON-файлы настроек |
| Frontend | Vue 3 + Pinia + Naive UI (`./frontend/src/pages/admin/tabs/BrandingTab.vue`, `./frontend/src/pages/admin/tabs/EmailTab.vue`, `./frontend/src/stores/branding.ts`) |
| Хранилище | Локальная ФС под `/data/branding/` |
| Файлы оформления | Логотип (`logo.*`), Фавикон (`favicon.*`), Фон входа (`login-bg.*`) |
| Настройки | Оформление (`settings.json`), Email/SMTP (`email-settings.json`) |
| Логирование событий | `branding.updated` (метаданные: `target` ∈ `settings`, `logo`, `favicon`, `login_bg`, `email_settings`, `email_test`) |

---

## 2. REST API

Все эндпойнты имеют базовый префикс `/api/v1`. Доступ к административным (`/admin/...`) эндпойнтам строго ограничен ролями.

| Метод | Путь | Назначение | Права |
|---|---|---|---|
| GET | `/api/v1/branding/settings` | Получить настройки оформления портала. Возвращает `BrandingSettingsOut`. | Авторизованный пользователь (`CurrentUser`) |
| PUT | `/api/v1/admin/branding/settings` | Сохранить настройки оформления портала. Принимает `BrandingSettings`. Пушит аудит-событие. | Редактор (`EditorDep`) |
| GET | `/api/v1/branding/logo` | Получить текущий логотип портала. Поддерживает метод HEAD. Кэширование: `Cache-Control: public, max-age=31536000, immutable`. | Публичный |
| POST | `/api/v1/admin/branding/logo` | Загрузить файл логотипа (multipart/form-data). | Редактор (`EditorDep`) |
| DELETE | `/api/v1/admin/branding/logo` | Сбросить логотип к значениям по умолчанию. | Редактор (`EditorDep`) |
| GET | `/api/v1/branding/favicon` | Получить текущий favicon. Поддерживает метод HEAD. Кэширование: `Cache-Control: public, max-age=3600`. | Публичный |
| POST | `/api/v1/admin/branding/favicon` | Загрузить файл favicon (multipart/form-data). | Редактор (`EditorDep`) |
| DELETE | `/api/v1/admin/branding/favicon` | Сбросить favicon к значениям по умолчанию. | Редактор (`EditorDep`) |
| GET | `/api/v1/branding/login-bg` | Получить фон страницы входа. Поддерживает метод HEAD. Кэширование: `Cache-Control: public, max-age=3600`. | Публичный |
| POST | `/api/v1/admin/branding/login-bg` | Загрузить фон страницы входа (multipart/form-data). | Редактор (`EditorDep`) |
| DELETE | `/api/v1/admin/branding/login-bg` | Сбросить фон страницы входа. | Редактор (`EditorDep`) |
| GET | `/api/v1/admin/email-settings` | Получить текущие настройки SMTP (пароль скрыт). | Администратор (`AdminDep`) |
| PUT | `/api/v1/admin/email-settings` | Сохранить настройки SMTP. Принимает `EmailSettingsIn`. Если передан пароль `***` или `null`, то старый пароль сохраняется. | Администратор (`AdminDep`) |
| POST | `/api/v1/admin/email-settings/test` | Отправить тестовое письмо для проверки SMTP. Запускается асинхронно в фоне. | Администратор (`AdminDep`) |

---

## 3. Хранилище и настройки

Все конфигурационные файлы и медиа-ресурсы сохраняются в директорию `/data/branding/` на локальной ФС. При первой записи директория создается автоматически.

### Настройки (JSON)
1. **Настройки брендинга (`/data/branding/settings.json`)**:
   Сериализованный объект схемы `BrandingSettings`. Запись производится атомарно с помощью хелпера `atomic_write` из `./backend/app/core/system_config/`.
2. **Настройки SMTP (`/data/branding/email-settings.json`)**:
   Содержит параметры подключения к почтовому серверу и пароль. Из соображений безопасности после записи для этого файла устанавливается маска прав `0o600` через `os.chmod`.

### Медиа-ресурсы (Изображения)
Файлы сохраняются под фиксированными префиксами имен. Расширение файла зависит от MIME-типа загруженного контента:
- **Логотип (`logo`)**: допустимы расширения `[".png", ".jpg", ".webp"]`. Поиск производится последовательно.
- **Иконка (`favicon`)**: допустимы расширения `[".png", ".jpg", ".webp", ".ico"]`.
- **Фон входа (`login-bg`)**: допустимы расширения `[".png", ".jpg", ".webp"]`.

При загрузке нового файла с другим расширением все "соседние" файлы с тем же префиксом, но старым расширением автоматически удаляются с диска во избежание конфликтов разрешения имен.

---

## 4. Frontend

### Pinia-стор брендинга (`./frontend/src/stores/branding.ts`)
Управляет состоянием кастомизации интерфейса:
- **Загрузка и сохранение**: Загружает данные через `/api/v1/branding/settings`.
- **Кэширование**: Хранит реактивный счетчик `assetVersion`. При загрузке новых ассетов счетчик обновляется (`Date.now()`), инвалидируя кэш картинок в браузере за счет query-параметра `?t={version}`.
- **Динамическая генерация стилей**:
  На основе выбранного `accent_color` (HEX) вычисляются цвета для hover/pressed состояний (путем конвертации HEX → RGB → HSL, уменьшения яркости на `8%` для hover и на `16%` для pressed, и конвертации обратно в HEX). CSS-переменные инжектируются напрямую в `document.documentElement`:
  ```css
  --color-brand-red: base_color;
  --color-brand-red-hover: hover_color;
  --color-brand-red-pressed: pressed_color;
  --color-brand-red-soft: base_color + "20" (альфа-канал 12%);
  --color-danger: base_color;
  ```
- **Темизация Naive UI**:
  Экспортирует вычисляемые объекты `lightOverrides` и `darkOverrides` для полной темизации Naive UI компонентов (в частности, элементов `common` и `Menu`), связывая их с динамическим акцентным цветом бренда.
- **Применение ресурсов**:
  Автоматически устанавливает `document.title` в значение `portal_name` и динамически обновляет элемент `<link rel="icon">` в `document.head` для применения кастомного favicon (создаёт новый элемент, если он отсутствует).

### Административный интерфейс
1. **Вкладка «Оформление» (`./frontend/src/pages/admin/tabs/BrandingTab.vue`)**:
   Позволяет загружать файлы логотипа, фавиконки и фонового изображения входа. Содержит форму для редактирования текстовых полей, выбора акцентного цвета через палитру и настройки системного информационного баннера (текст, тип баннера `info/warning/error/success` и срок его действия).
2. **Вкладка «Email» (`./frontend/src/pages/admin/tabs/EmailTab.vue`)**:
   Обеспечивает ввод SMTP-настроек, выбор метода шифрования (None / TLS / STARTTLS) и запуск модального окна для отправки проверочного письма.

---

## 5. Особенности и нюансы

- **Ограничения размеров**:
  Максимальный размер любого загружаемого файла (логотипа, favicon, фонового изображения) составляет **2 МБ**. Это ограничение жестко контролируется как на бэкенде константой `_MAX_IMAGE_SIZE`, так и на фронтенде переменной `BRANDING_MAX_SIZE`.
- **Связь с системными настройками (ADR-037)**:
  В эндпойнте получения настроек брендинга `get_settings()` динамически подгружаются глобальные системные настройки с помощью `load_system_settings()`. Если в системе включена интеграция внешней видеогалереи (`sys.video_gallery_url`), этот домен автоматически добавляется в список `allowed_iframe_origins`.
- **Обработка пароля SMTP**:
  При запросе GET `/api/v1/admin/email-settings` пароль никогда не передается клиенту, а возвращается булевый флаг `password_set`. При сохранении настроек через PUT, если в поле password передано значение `***` или `null`, бэкенд оставляет текущий сохраненный пароль без изменений.
- **Отправка тестового письма**:
  В отличие от основной инфраструктуры писем, работающей через транзакционную outbox-таблицу в базе данных (подробнее см. `./docs/email.md`), отправка тестового письма производится **напрямую и асинхронно** через `BackgroundTasks` FastAPI с помощью встроенной функции `_send_test_email()`. Она собирает MIME-сообщение (`MIMEMultipart`) с текстовой и HTML-версиями и отправляет его через `aiosmtplib.send` напрямую на SMTP-сервер с текущими (еще, возможно, не примененными глобально) параметрами. Любые ошибки отправки логируются в `branding.test_email_failed`.
