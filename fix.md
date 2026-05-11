# Code Review — Список проблем

> Статус: только описание, без исправлений.
> Severity: **P0** = крэш / потеря данных · **P1** = серьёзный баг · **P2** = архитектурная проблема / костыль

---

## Backend

### P0 — Критические

---

#### 1. Двойная отправка in-app уведомлений при публикации новости
**Файл:** `backend/app/worker/tasks/news.py` — функция `_enqueue_news_notifications` (~строка 53)

`_enqueue_news_notifications` делает две вещи одновременно:
1. Ставит в очередь ARQ-задачу `notify_news_published`
2. **И сразу** напрямую вызывает `notify_users_news_published`

Задача `notify_news_published` (`worker/tasks/notifications.py`) сама вызывает `notify_users_news_published` в конце. Итог: каждый пользователь получает **два одинаковых** in-app уведомления при каждой публикации новости.

**Исправление:** убрать прямой вызов `notify_users_news_published` из `_enqueue_news_notifications` — оставить только постановку в очередь ARQ-задачи.

**Подтверждено:** ✓ Да. `worker/tasks/news.py:69-85` ставит ARQ-задачу `notify_news_published` и тут же вызывает `notify_users_news_published`. Сам `worker/tasks/notifications.py:190` повторно вызывает ту же функцию.

**Сложность исправления:** Тривиальная (удалить блок `async with AsyncSessionLocal()` из `_enqueue_news_notifications`, ~10 строк).

**Как пользователь столкнётся:** Каждый раз при ручной публикации или срабатывании cron-задачи `publish_scheduled_news` все целевые пользователи получают 2 одинаковых in-app уведомления в SSE-стриме / счётчик `unread_count` растёт вдвое. Видно сразу после первой публикации новости.

---

#### 2. Неверная конвертация `offset → page` в API новостей
**Файл:** `backend/app/api/news.py` — строка ~72

```python
if offset is not None:
    page = (offset // page_size) + 1
```

Для `offset=10, page_size=20`: `page = 0 + 1 = 1` → сервис вернёт строки 0–19 вместо 10–29.
Любой клиент, который передаёт `offset` не кратный `page_size`, получает неверные данные.

**Исправление:** добавить параметр `offset_override` в `news_svc.get_news_list` и передавать `offset` напрямую, минуя конвертацию в `page`.

**Подтверждено:** ✓ Да. `backend/app/api/news.py:71-72` — формула `page = (offset // page_size) + 1` теряет остаток от деления. При `offset=10, page_size=20` → `page=1` → вернутся записи 0–19, а не 10–29.

**Сложность исправления:** Средняя — нужно поправить и API-слой, и `services/news.py:get_news_list`, чтобы он понимал явный offset; затронут и шейп параметров пагинации.

**Как пользователь столкнётся:** Любой клиент (например, infinite-scroll списка новостей или внешний скрипт), передающий `offset` не кратный `page_size`, получит дубликаты на стыке страниц или вообще пропустит часть новостей. Воспроизводится запросом `GET /api/v1/news?offset=10&page_size=20`.

---

#### 3. `total` в `/kb/articles` считается до ACL-фильтрации
**Файл:** `backend/app/api/kb/articles.py` — строка ~98

```python
count_stmt = select(func.count()).select_from(stmt.subquery())
total = (await db.execute(count_stmt)).scalar_one()   # до ACL

...
perm_map = await batch_resolve_article_permissions(...)

items = []
for a in articles:
    perm = perm_map.get(a.id)
    if perm is None:
        continue                 # часть статей скрыта
    items.append(...)

return KbArticleList(items=items, total=total, ...)  # total завышен
```

Клиент получает `total=100`, но `items` содержит только те статьи, к которым у пользователя есть ACL-доступ (например, 70). Пагинация на фронте сломана.

**Исправление:** убрать `count_stmt` до фильтрации; загрузить все совпадающие статьи без `LIMIT/OFFSET`, применить ACL, затем `total = len(filtered)`, `items = filtered[offset:offset+limit]`.

**Подтверждено:** ✓ Да. `backend/app/api/kb/articles.py:98-139` — `total` берётся из COUNT по неотфильтрованному набору, после чего `perm_map` отсекает часть статей в Python.

**Сложность исправления:** Высокая. Простое предложенное «загрузить всё → отфильтровать → отдать страницу» уничтожит производительность на больших разделах. Правильное решение требует push-down ACL-фильтра в SQL (через CTE с явными разрешениями на section/article), что затрагивает `permissions/kb.py` и SQL-схему ACL.

**Как пользователь столкнётся:** На странице со списком статей KB у обычного пользователя пагинация показывает «1–20 из 100», но фактически отрисовываются 7 строк; кнопки следующих страниц возвращают пустые экраны или меньше элементов. Особенно заметно в разделах с приватными статьями.

---

#### 4. `total` в поиске по KB обрезан до `kb_fetch_limit`
**Файл:** `backend/app/api/search.py` — строка ~104

```python
if single_type:
    total = len(article_results)   # максимум kb_fetch_limit, не реальный count
    return SearchResponse(items=article_results[offset:offset+limit], total=total, ...)
```

`kb_fetch_limit = (offset + limit) * 5`. Если доступных статей больше — `total` занижен.
Для news/link/user при `single_type=True` делается отдельный `SELECT count(*)`, а для статей KB — нет.

**Исправление:** добавить `SELECT count(*)` по тем же условиям без `LIMIT`, как сделано для news/link/user.

**Подтверждено:** ✓ Да. `backend/app/api/search.py:55,87,105` — `kb_fetch_limit = (offset + limit) * _KB_FETCH_MULTIPLIER`; `article_results` строится из этого ограниченного набора; `total = len(article_results)` ⇒ потолок занижен. Но: после `count(*)` всё равно нужно учесть ACL (та же проблема, что в #3), иначе `total` опять будет завышен.

**Сложность исправления:** Средняя — добавить count для article похоже на news; одновременно нужно решить проблему ACL-неучёта (см. #3), иначе фикс будет половинчатый.

**Как пользователь столкнётся:** При глобальном поиске с фильтром type=article и большим количеством совпадений пользователь видит «найдено 50 статей», хотя их сотни; пагинация в результатах не работает (кнопка «следующая страница» возвращает пустоту).

---

### P1 — Серьёзные баги

---

#### 5. Устаревший `view_count` в ответе детальной страницы новости
**Файл:** `backend/app/api/news.py` — строка ~117

```python
news = await news_svc.get_news_by_id(db, news_id)   # view_count = N
...
await news_svc.increment_view_count(db, news_id)    # в БД: N+1
return news                                          # возвращает N, а не N+1
```

**Исправление:** после `increment_view_count` добавить `await db.refresh(news, attribute_names=['view_count'])`.

**Подтверждено:** ✓ Да. `backend/app/api/news.py:111-122` — `get_news_by_id` грузит объект, `increment_view_count` инкрементирует в БД, но возвращается тот же in-memory объект без refresh.

**Сложность исправления:** Тривиальная (одна строка `await db.refresh(...)`).

**Как пользователь столкнётся:** На детальной странице новости счётчик просмотров отстаёт ровно на 1 (или больше, если есть параллельные просмотры). Видно при F5 на странице новости: новое значение появится только при следующей загрузке. Заметит наблюдательный редактор или QA.

---

#### 6. TOCTOU race condition при генерации slug папки фотогалереи
**Файл:** `backend/app/api/photos/folders.py` — строка ~127

Уникальность slug проверяется через `SELECT count(*)`, затем делается `INSERT`. Два конкурентных запроса оба пройдут проверку и один упадёт с необработанным `IntegrityError` (→ HTTP 500), хотя уникальный индекс `uq_photo_folders_parent_slug` существует.

**Исправление:** обернуть `await db.commit()` в `try/except IntegrityError` и возвращать HTTP 409.

**Подтверждено:** ✓ Да. `backend/app/api/photos/folders.py:127-141` — цикл проверки уникальности через `SELECT count` + `db.add` + `db.commit` без обработки `IntegrityError`. Уникальный индекс существует (упомянут в задаче и в Alembic-миграциях), поэтому race приведёт к 500.

**Сложность исправления:** Низкая (обернуть commit в try/except и сделать retry или 409).

**Как пользователь столкнётся:** Два администратора/менеджера одновременно создают папки с одинаковыми именами в одном родителе → один получает HTTP 500 («Internal Server Error») вместо 409, в логах — необработанный `IntegrityError`. Редко, но воспроизводимо при ботах/импорте.

---

#### 7. Повреждение `fs_path` потомков при пустом `old_fs_path`
**Файл:** `backend/app/api/photos/folders.py` — строка ~285

```python
if old_path:   # проверяется только path, не fs_path
    await db.execute(
        update(PhotoFolder)
        .values(
            fs_path=func.concat(
                new_fs_path,
                func.substring(PhotoFolder.fs_path, len(old_fs_path) + 1)
                # если old_fs_path == '' → substring(col, 1) → вся строка
            )
        )
    )
```

Если `old_fs_path == ""` при непустом `old_path`, каждый потомок получит `new_fs_path + весь_свой_старый_fs_path` вместо правильного суффикса. Дерево папок на ФС становится несогласованным навсегда.

**Исправление:** разделить обновление `path` и `fs_path`. Обновлять `fs_path` потомков только когда `old_fs_path` непустой (`if old_fs_path:`), иначе исключить колонку из `VALUES`.

**Подтверждено:** ✓ Частично. `backend/app/api/photos/folders.py:280-298` действительно использует `substring(PhotoFolder.fs_path, len(old_fs_path) + 1)` внутри одного `update`, проверка идёт только по `old_path`. Однако в обычном потоке `old_fs_path` пустым быть не может (корневые папки получают `fs_path = fs_seg` при создании). Сценарий требует ручного исторического NULL/`""` в БД (миграции, ошибки данных).

**Сложность исправления:** Низкая (один `if`/разделить два `update`), но требует тесты с фикстурой папки без `fs_path`.

**Как пользователь столкнётся:** В прод-окружении с импортированными до введения `fs_path` папками (или после миграции) — перемещение такой корневой папки в новый родительский каталог сломает физические пути всех её детей; фотографии не откроются с диска, превью посыпятся. Сценарий редкий, но восстановление требует ручной правки `fs_path` в БД и переноса файлов.

---

#### 8. Soft-deleted пользователи возвращаются в admin groups endpoint
**Файл:** `backend/app/api/users.py` — строка ~320

```python
result = await db.execute(select(User).where(User.id == user_id))
```

Нет фильтра `User.deleted_at.is_(None)`. Запрос групп удалённого пользователя возвращает данные вместо 404.

**Исправление:** добавить `.where(User.deleted_at.is_(None))`.

**Подтверждено:** ✓ Да. `backend/app/api/users.py:320` — простой `select(User).where(User.id == user_id)` без фильтра по `deleted_at`. То же самое в `admin_patch_user_profile:339` (та же дыра).

**Сложность исправления:** Тривиальная (добавить условие в where).

**Как пользователь столкнётся:** Админ в UI «удалённые пользователи» открывает группы soft-deleted аккаунта и видит данные вместо 404 — путаница, риск ошибочного восстановления привилегий. Малая частота, но утечка состояния.

---

#### 9. Потеря отслеживания активной сессии при `invalidate_all_user_sessions`
**Файл:** `backend/app/services/session.py` — строка ~122

```python
for sid in session_ids:
    if except_session_id and sid == except_session_id:
        continue
    await redis.delete(_session_key(sid))
    count += 1
await redis.delete(key)   # удаляет весь сет, включая except_session_id!
```

Когда `except_session_id` указан (например, при смене пароля — оставляем текущую сессию), активная сессия перестаёт отслеживаться в `user_sessions:{user_id}` и больше не может быть инвалидирована через эту функцию.

**Исправление:** если `except_session_id` указан — вместо `await redis.delete(key)` использовать `await redis.srem(key, *invalidated_sids)`, сохраняя запись об активной сессии в сете.

**Подтверждено:** ✓ Да. `backend/app/services/session.py:122` — безусловный `redis.delete(key)`, который удаляет весь set, включая `except_session_id`.

**Сложность исправления:** Низкая (заменить delete на srem или сделать ветку).

**Как пользователь столкнётся:** После смены пароля или ручного действия «выйти со всех устройств кроме текущего» текущая сессия живёт, но не отслеживается в `user_sessions:{user_id}`. Если позже админ нажмёт «терминировать все сессии» — текущая сессия не будет инвалидирована, пользователь продолжит работать с устаревшими привилегиями. Скрытый баг безопасности.

---

#### 10. Блокирующий `os.walk` в async-функции воркера
**Файл:** `backend/app/worker/tasks/photos.py` — строка ~444

`os.walk(str(import_root))` — синхронная блокирующая операция внутри `async def import_scan_run`. Для больших директорий или медленного хранилища блокирует event loop ARQ-воркера, «голодая» все остальные задачи.

**Исправление:** `walk_result = await asyncio.to_thread(list, os.walk(str(import_root)))`.

**Подтверждено:** ✓ Да. `backend/app/worker/tasks/photos.py:444` — `for ... in os.walk(...)` внутри `async def import_scan_run`. Сам цикл ещё делает `await` внутри, но обход директорий — синхронный stat-IO.

**Сложность исправления:** Низкая, но предложенная формулировка с `list(os.walk(...))` некорректна: `list(...)` всё равно полностью исчерпает генератор синхронно до возврата в `to_thread`. Правильнее завернуть всё чтение в отдельную функцию или выполнять `next()` через `to_thread` по чанкам.

**Как пользователь столкнётся:** При больших импортируемых архивах (тысячи папок) воркер ARQ замирает — другие задачи (отправка email, миниатюры) встают в очередь, SSE/keepalive могут тайм-аутиться. Заметят при первом массовом импорте фотогалереи.

---

#### 11. N+1 запросов в Keycloak при синхронизации пользователей
**Файл:** `backend/app/worker/tasks/news.py` — функция `sync_users_from_keycloak` (~строка 185)

```python
for ku in kc_users:
    groups = await kc_service.get_user_groups(ku["id"])   # 1 HTTP-запрос на пользователя
```

Для 1000 пользователей — 1000 последовательных HTTP-запросов к Keycloak. Задача занимает минуты и может повторяться.

**Исправление:** получать группы пользователей пачками через Keycloak Admin API (если поддерживается) или подключать группы через `briefRepresentation=false` при запросе списка пользователей.

**Подтверждено:** ✓ Да. `backend/app/worker/tasks/news.py:185` — `await kc_service.get_user_groups(ku["id"])` внутри цикла по `kc_users`.

**Сложность исправления:** Средняя. Keycloak Admin API не отдаёт группы массово; типичное решение — один запрос на группу с `GET /groups/{id}/members` и инверсия структуры. Требует переделки `kc_service` и аккуратной пагинации.

**Как пользователь столкнётся:** Cron-задача синхронизации (каждые N минут) длится минутами на 1000+ пользователей; в логах копятся запросы к Keycloak; при таймаутах задача рестартует и переписывает `updated_at` всем юзерам. Админ видит «kc:sync_last_run.count» отстаёт от реальности.

---

### P2 — Архитектурные проблемы

---

#### 12. Утечка Redis connection pool в health check
**Файл:** `backend/app/api/health.py` — строка ~14

```python
def get_redis(request: Request) -> Redis:
    redis = getattr(request.app.state, "redis", None)
    if redis is None:
        return Redis.from_url(settings.redis_url, decode_responses=True)  # новый pool, никогда не закрывается
    return redis
```

Каждое обращение к `/ready` в fallback-ветке создаёт новый connection pool без закрытия.

**Исправление:** убрать fallback — если `app.state.redis` равен `None`, выбрасывать `RuntimeError` (что корректно отобразится как ошибка readiness probe).

**Подтверждено:** ✓ Да. `backend/app/api/health.py:14-18` — `Redis.from_url(...)` создаёт новый pool без сохранения/закрытия. Однако в нормальном lifecycle `app.state.redis` всегда установлен, путь fallback почти не активируется.

**Сложность исправления:** Тривиальная (удалить fallback).

**Как пользователь столкнётся:** Если по какой-то причине `app.state.redis` равен None (ранний этап lifespan, тестовая среда), k8s/мониторинг будет периодически дёргать `/ready` → каждое обращение открывает новые TCP-соединения к Redis, накапливая `CLOSE_WAIT`/идущие неиспользуемые pool'ы. На прод. практике почти невидимо.

---

#### 13. SSE использует монотонные часы → stale-записи после перезапуска
**Файл:** `backend/app/api/notifications.py` — строка ~230 и ~275

`asyncio.get_running_loop().time()` возвращает монотонное время, стартующее около 0 при каждом запуске процесса. Записи в Redis-sorted-set с большими score-значениями от предыдущего запуска не удаляются `ZREMRANGEBYSCORE(key, 0, now)` и навсегда занимают слоты подключений.

**Исправление:** заменить на `time.time()` (UNIX timestamp).

**Подтверждено:** ✓ Да. `backend/app/api/notifications.py:230,275` — используется `asyncio.get_running_loop().time()` (монотонные часы процесса).

**Сложность исправления:** Тривиальная (заменить на `time.time()` и согласовать Lua-скрипт `_LUA_CONN_ADD`).

**Как пользователь столкнётся:** После рестарта pod'а API записи о соединениях, оставленных предыдущим процессом, не удаляются `ZREMRANGEBYSCORE(key, 0, now)` (их score = большое число из старого монотонного отсчёта). Постепенно лимит `_max_per_user` / `_max_global` забивается «мертвыми» соединениями и легитимные клиенты получают 429/недоступность SSE. Заметно через несколько дней аптайма с рестартами.

---

#### 14. 4 непоследовательных Redis-команды в SSE keepalive без pipeline
**Файл:** `backend/app/api/notifications.py` — строка ~232

```python
await redis.zadd(conn_key, {connection_id: new_score})
await redis.zadd(_SSE_GLOBAL_CONN_KEY, {connection_id: new_score})
await redis.expire(conn_key, _SSE_CONNECTION_TTL * 2)
await redis.expire(_SSE_GLOBAL_CONN_KEY, _SSE_CONNECTION_TTL * 2)
```

Если `EXPIRE` упадёт после `ZADD` — ключ существует без TTL и накапливается вечно.

**Исправление:** завернуть все 4 команды в `async with redis.pipeline(transaction=True) as pipe`.

**Подтверждено:** ✓ Да. `backend/app/api/notifications.py:232-235` — 4 await-вызова подряд без MULTI/pipeline. Если between `ZADD` и `EXPIRE` процесс упадёт или Redis сбросит TCP, ключ остаётся без TTL.

**Сложность исправления:** Низкая (обернуть в pipeline).

**Как пользователь столкнётся:** Длительный uptime API + редкие падения соединения с Redis → ключи `sse:conn:*` остаются без TTL, постепенно растут — потенциальный OOM Redis на длинном горизонте. Невидимо в моменте, проявляется как медленная утечка памяти.

---

#### 15. Небезопасное удаление distributed lock в задаче files
**Файл:** `backend/app/worker/tasks/files.py` — строка ~131

```python
finally:
    if redis is not None:
        await redis.delete(_SYNC_LOCK_KEY)   # безусловное удаление
```

Если выполнение задачи превышает TTL блокировки (300 с), другой воркер успевает захватить lock. Первый воркер в `finally` удалит чужую блокировку, открывая параллельный запуск.

**Исправление:** при захвате блокировки сохранять уникальный токен (`secrets.token_hex(16)`), при освобождении сверять значение через Lua-скрипт или `GET + DEL`.

**Подтверждено:** ✓ Да. `backend/app/worker/tasks/files.py:41` использует `redis.set(_SYNC_LOCK_KEY, "1", nx=True, ex=300)`, а в finally:131 — безусловное `redis.delete(_SYNC_LOCK_KEY)`. Токен не сохраняется.

**Сложность исправления:** Низкая (стандартный паттерн «fence token + Lua compare-and-delete»).

**Как пользователь столкнётся:** При очень длинном первичном BFS-обходе Nextcloud (>300с) второй экземпляр воркера захватывает lock, начинает свой обход, а первый — освобождает чужую блокировку. Третий воркер может зайти параллельно, в логах появляются дубликаты `files.startup_sync.done`. Низкая частота, актуально при большой иерархии NC.

---

#### 16. Синхронный файловый I/O блокирует event loop в `files_acl_persistence`
**Файл:** `backend/app/services/files_acl_persistence.py` — строки ~85, ~90

```python
async def save_folder_perms(nc_path: str, entries: list[AclEntry]) -> None:
    async with _get_write_lock():
        data = _read_raw()    # синхронный disk I/O
        ...
        _write_raw(data)      # синхронный disk I/O
```

`asyncio.Lock` защищает от параллельного доступа, но не от блокировки event loop.

**Исправление:** `data = await asyncio.to_thread(_read_raw)` и `await asyncio.to_thread(_write_raw, data)`.

**Подтверждено:** ✓ Да. `backend/app/services/files_acl_persistence.py:82-99` — `_read_raw()`/`_write_raw()` синхронные (json.dump + fdopen) вызываются прямо в async-функциях.

**Сложность исправления:** Тривиальная (две `asyncio.to_thread`-обёртки).

**Как пользователь столкнётся:** Каждое изменение ACL на папке файлов = чтение всего `files-acl.json` + полная запись. На больших инсталляциях с тысячами папок задержка десятки мс, в это время API не обслуживает другие запросы того же воркера. Заметно при массовых импортах или скриптах автоматизации.

---

#### 17. Синхронный файловый I/O в `bootstrap` эндпоинте
**Файл:** `backend/app/api/bootstrap.py` — функция `_build_branding` (~строка 61)

`_load_settings()`, `_find_file()`, `load_system_settings()` — все читают файлы синхронно внутри async-обработчика. Каждый запрос `/api/v1/bootstrap` блокирует event loop на время дисковых операций.

**Исправление:** `branding = await asyncio.to_thread(_build_branding)`.

**Подтверждено:** ✓ Да. `backend/app/api/bootstrap.py:61-73,121` — `_build_branding()` вызывается синхронно. Внутри: `_load_settings()` (JSON), `_find_file(...)` (несколько `Path.exists`), `load_system_settings()` (JSON). Все блокирующие.

**Сложность исправления:** Тривиальная (одна `asyncio.to_thread`).

**Как пользователь столкнётся:** При первой загрузке SPA каждый клиент вызывает `/api/v1/bootstrap`. Если файловая система медленная (NFS, сетевой том), все остальные запросы в этом воркере ждут. На стресс-нагрузке (одновременный логин 100+ пользователей) видны редкие тайм-ауты и просадка p99 latency.

---

---

## Frontend

### P0 — Критические

---

#### 18. Бесконечный redirect loop при недоступном backend
**Файл:** `frontend/src/router.ts` — строка ~185

```typescript
if (result === 'network_error' && to.meta.requiresAuth) {
    return { name: 'home' }   // 'home' тоже requiresAuth → гард сработает снова
}
```

При `network_error` → редирект на `home` → гард снова вызывает `loadBootstrap()` → снова `network_error` → бесконечный цикл. Пользователь зависает.

**Исправление:** редиректить на `{ name: 'auth-error' }` (публичный маршрут) вместо `home`.

**Подтверждено:** ✓ Частично. `frontend/src/router.ts:185-186` — да, на `network_error` редирект на `home`, который наследует `requiresAuth: true` (строка 69). Однако Vue Router 4 имеет внутренний guard от infinite redirect и выкинет ошибку `Detected an infinite redirection` после ~10 циклов. То есть «бесконечный» лежит на стороне навигации; UX всё равно сломан (белый экран/ошибка консоли).

**Сложность исправления:** Низкая. Нужно добавить маршрут `auth-error` (public) и страницу-заглушку, либо использовать `false` (отмена навигации) + показать сообщение.

**Как пользователь столкнётся:** При отключённом backend (или CORS-ошибке) пользователь, переходя по любому URL с `requiresAuth`, видит пустой экран, в консоли — `NavigationDuplicated` / `Detected infinite redirection`. F5 не помогает.

---

### P1 — Серьёзные баги

---

#### 19. Результат `loadUser()` игнорируется в AuthCallbackPage
**Файл:** `frontend/src/pages/AuthCallbackPage.vue` — строка ~17

```typescript
onMounted(async () => {
    await auth.loadUser()
    router.replace('/')    // всегда, даже если загрузка провалилась
})
```

Если `loadUser()` вернул `'unauthenticated'` или `'network_error'`, пользователь всё равно редиректится на `/` (защищённый маршрут), что вызывает повторные редиректы и нестабильный auth-flow.

**Исправление:** проверять результат: `'ok'` → `/`, `'unauthenticated'` → SSO/login, `'network_error'` → `/auth/error`.

**Подтверждено:** ✓ Да. `frontend/src/pages/AuthCallbackPage.vue:16-19` — результат `loadUser()` не используется, `router.replace('/')` безусловно.

**Сложность исправления:** Тривиальная (switch по строке-результату).

**Как пользователь столкнётся:** После OIDC-редиректа, если cookie выставился криво или сеть моргнула — пользователь попадает на `/` (requiresAuth), guard инициирует новый SSO-цикл. Возможна петля «callback → / → SSO → callback». В лучшем случае — просто долгая загрузка, в худшем — выбивает на login Keycloak повторно.

---

#### 20. Race condition: галерея и вложения не инициализируются при редактировании новости
**Файл:** `frontend/src/pages/NewsFormPage.vue` — строки ~337, ~345

```typescript
watch(editNewsData, (news) => {
    if (news && !formInitialized.value) {
        formInitialized.value = true   // флаг становится true
        ...
    }
})

watch(editGalleryData, (gallery) => {
    if (gallery && !formInitialized.value) galleryImages.value = gallery  // никогда не выполнится
})

watch(editAttachmentsData, (atts) => {
    if (atts && !formInitialized.value) attachments.value = atts          // никогда не выполнится
})
```

`editNewsData` приходит раньше (отдельный API-запрос, более быстрый). К моменту ответа от gallery/attachments `formInitialized` уже `true`, и данные не применяются. Редактор открывается с пустой галереей и без вложений.

**Исправление:** использовать отдельные флаги для основной формы и для медиа, либо убрать условие `!formInitialized.value` из вотчеров галереи/вложений.

**Подтверждено:** ✓ Да. `frontend/src/pages/NewsFormPage.vue:317-346` — флаг `formInitialized` ставится только в первом вотчере и блокирует два других.

**Сложность исправления:** Тривиальная (отдельные флаги `galleryInitialized`, `attachmentsInitialized`).

**Как пользователь столкнётся:** Редактор открывает существующую новость с галереей/вложениями. В большинстве случаев `editNewsData` приходит первым (это лёгкий запрос), а галерея ещё грузится. После «инициализации» формы поле галереи остаётся пустым — пользователь думает, что вложения слетели, может пересохранить новость и затереть их. Высокий риск потери данных.

---

#### 21. Параллельные autosave-запросы из `setInterval` в NewsFormPage
**Файл:** `frontend/src/pages/NewsFormPage.vue` — строка ~360

`setInterval` с async-коллбэком не защищён от реэнтрантности. Если `saveDraft` выполняется дольше 30 с (медленная сеть), следующий тик стартует второй параллельный PUT-запрос. Оба перезаписывают черновик, последний «выигрывает» и затирает правки.

**Исправление:** добавить guard `autoSaveInFlight`, блокирующий повторный старт; либо заменить `setInterval` на self-scheduling `setTimeout`, запускаемый только после завершения предыдущего autosave.

**Подтверждено:** ✓ Частично. `frontend/src/pages/NewsFormPage.vue:357-372` — `setInterval` с async-коллбэком. Существующая защита `if (saving.value) return` ловит только конфликт с ручным сохранением, не с собственным предыдущим тиком. Аналогичный паттерн в `KbArticleFormPage.vue:218`.

**Сложность исправления:** Тривиальная (добавить `autoSaveInFlight` ref).

**Как пользователь столкнётся:** Редактор новости с медленной сетью (3G, VPN). Каждые 30с тикает autosave. Если PUT задерживается > 30с, два запроса летят параллельно — последний может вернуть устаревшее содержимое и затереть свежие правки пользователя. Очень редко, но критично.

---

#### 22. Race при повторном запуске очереди загрузки фото
**Файл:** `frontend/src/composables/usePhotoUpload.ts` — строка ~49

`runUploadQueue` перезаписывает `_abortController` и `uploadQueue` при каждом вызове. Если функция вызвана через `onDrop` пока предыдущий upload ещё активен, прогресс-обновления старого цикла записываются в индексы нового `uploadQueue`, приводя к некорректным статусам.

**Исправление:** при уже активном `uploadingActive` блокировать повторный старт или сначала вызывать `abortUpload()` и дожидаться завершения предыдущего.

**Подтверждено:** ✓ Да. `frontend/src/composables/usePhotoUpload.ts:49-78` — `runUploadQueue` сбрасывает `_abortController` и `uploadQueue` без проверки незавершённой загрузки. Колбэк прогресса прежнего цикла продолжит писать в новые индексы.

**Сложность исправления:** Низкая (проверка `uploadingActive` в начале, либо `await abortUpload()`).

**Как пользователь столкнётся:** Пользователь перетащил в дроп-зону пакет фото, не дождался окончания и сразу перетащил ещё один → прогресс-бары начинают «прыгать», статус некоторых файлов застывает на `uploading`, итоговый счётчик «N из M» не совпадает. Достаточно одного нетерпеливого пользователя.

---

#### 23. Stale-ответ перезаписывает комментарии/версии новой статьи
**Файл:** `frontend/src/pages/KbArticlePage.vue` — строка ~266

```typescript
watch(articleId, async () => {
    await loadComments()
    await loadVersions()
})

async function loadComments() {
    const res = await fetchComments(articleId.value, ...)
    comments.value = res.items   // нет проверки актуальности articleId
}
```

При быстрой навигации между статьями медленный ответ для предыдущей статьи записывает свои комментарии/версии поверх уже загруженных данных текущей статьи.

**Исправление:** сохранять `const id = articleId.value` до `await`, после ответа проверять `if (id !== articleId.value) return`.

**Подтверждено:** ✓ Да. `frontend/src/pages/KbArticlePage.vue:266-283,377-380` — функции `loadComments`/`loadVersions` используют `articleId.value` после await без guard'а.

**Сложность исправления:** Низкая (паттерн «capture-then-check» в двух функциях).

**Как пользователь столкнётся:** Пользователь быстро кликает в боковой панели по разным KB-статьям. При плохой сети ответ за статью №1 приходит позже, чем для №2; в открытой статье №2 появляются комментарии статьи №1. Заметит активный читатель wiki.

---

#### 24. `Promise.all` на главной странице роняет всю загрузку при ошибке одного источника
**Файл:** `frontend/src/pages/HomePage.vue` — строка ~190

```typescript
const [res, , cats] = await Promise.all([
    fetchNewsList(...),
    linksStore.loadLinks(),
    fetchNewsCategories(),
])
```

Если любой из трёх запросов упадёт (например, недоступен сервис новостей), пользователь не увидит ничего — ни ссылки, ни категории, даже если остальные запросы успешны.

**Исправление:** заменить на `Promise.allSettled` и обрабатывать каждый результат независимо.

**Подтверждено:** ✓ Да. `frontend/src/pages/HomePage.vue:190-200` — `Promise.all` без `try/catch` для каждого источника; общий `finally` только выключает спиннер.

**Сложность исправления:** Тривиальная (`allSettled` + 3 проверки status).

**Как пользователь столкнётся:** Один из бэкенд-сервисов (например, links-store) временно недоступен или 5xx — главная страница пустая, спиннер ушёл, но ни новостей, ни ссылок, ни категорий. В консоли — unhandled rejection.

---

#### 25. Нет обработки ошибок при первичной загрузке KbArticleFormPage
**Файл:** `frontend/src/pages/KbArticleFormPage.vue` — строка ~204

```typescript
onMounted(async () => {
    const [secRes] = await Promise.all([fetchSections()])   // без try/catch
    ...
    const art = await fetchArticle(articleId.value)          // без try/catch
    ...
})
```

Сетевая ошибка или 404 → unhandled rejection. Пользователь видит пустую форму без какого-либо сообщения.

**Исправление:** обернуть в `try/catch`, при 404 — редирект на список, при других ошибках — показывать `message.error`.

**Подтверждено:** ✓ Да. `frontend/src/pages/KbArticleFormPage.vue:204-221` — `onMounted` без try/catch; `Promise.all([fetchSections()])` и `fetchArticle` могут отклониться без обработки.

**Сложность исправления:** Тривиальная (try/catch + проверка `err.response?.status === 404`).

**Как пользователь столкнётся:** Открыть `/kb/articles/<deleted-id>/edit` — пустая форма, нет уведомления, нечего сохранить. Любая сетевая ошибка приводит к зависанию редактора без feedback.

---

### P2 — Архитектурные проблемы

---

#### 26. AbortSignal передаётся только в news-запрос при глобальном поиске
**Файл:** `frontend/src/composables/useGlobalSearch.ts` — строка ~34

```typescript
await Promise.allSettled([
    fetchNewsList(..., { signal }),    // ✓ отменяется
    globalSearch(query, { limit: kbLimit }),        // ✗ продолжает выполняться
    fetchUsers({ q: query, page_size: userLimit }), // ✗ продолжает выполняться
])
```

При быстром вводе (debounce) устаревшие запросы к KB и пользователям продолжают выполняться, создавая лишнюю нагрузку и потенциально перезаписывая актуальные результаты.

**Исправление:** добавить поддержку `signal` в `globalSearch` (`api/kb.ts`) и `fetchUsers` (`api/users.ts`), передавать его из `runGlobalSearch`.

**Подтверждено:** ✓ Да. `frontend/src/composables/useGlobalSearch.ts:29-36` — только `fetchNewsList` принимает `signal`; `globalSearch` и `fetchUsers` вызываются без него.

**Сложность исправления:** Низкая (расширить сигнатуры API-клиентов и пробросить signal). Затрагивает api-слой.

**Как пользователь столкнётся:** Невидимо в UX, но бэкенд получает в N раз больше KB-поисков при быстром наборе. Также возможна гонка: устаревший ответ может перерисовать результаты, если бы не было сортировки по последнему завершившемуся (текущая реализация присваивает результаты только когда все три promise resolved). На практике — лишняя нагрузка на API.

---

#### 27. Накопление stale DOM-ссылок в `cardRefs` на MyFeedbackPage
**Файл:** `frontend/src/pages/MyFeedbackPage.vue` — строка ~133

```typescript
function setCardRef(id: string, el: any) {
    if (el && el.$el) cardRefs.set(id, el.$el as HTMLElement)
    else if (el instanceof HTMLElement) cardRefs.set(id, el)
    // el === null при unmount — не удаляется из Map
}
```

При удалении/перерисовке карточек `null`-коллбэк игнорируется, DOM-узлы удерживаются в памяти.

**Исправление:** `if (!el) { cardRefs.delete(id); return }` в начале функции.

**Подтверждено:** ✓ Да. `frontend/src/pages/MyFeedbackPage.vue:133-136` — на `el === null` функция тихо игнорирует, в Map остаются ссылки на размонтированные узлы.

**Сложность исправления:** Тривиальная (одна строка).

**Как пользователь столкнётся:** При листании списка фидбэка (бесконечный scroll, фильтры) Map растёт; DOM-узлы не освобождаются GC. На длинной сессии — заметный рост памяти вкладки, в DevTools видно «detached HTML element». Не вызывает функционального бага, но утечка памяти.

---

## Итого

| Severity | Кол-во |
|----------|--------|
| P0       | 4      |
| P1       | 8      |
| P2       | 7      |
| **Всего**| **19** |
