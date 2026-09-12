# Миграция Production: GHCR → Forgejo Container Registry

> **Статус:** процедура отработана на проде `webmage` 2026-08-11, образы `v1.8.0`.
> Связанные ADR (в [`adr.md`](./adr.md)): ADR-045 (registry-pull deploy),
> ADR-046 (deploy-bundle без клона репо), ADR-047 (semver-lock),
> ADR-049 (переезд GitHub → Forgejo).

## Когда применять

Один раз на каждом prod-сервере, который ещё ездит на образах из GitHub Container
Registry (`ghcr.io/veryshuu/*`) — после того, как репозиторий переехал на Forgejo
(`forgejo.mage.ru/mage/portal`) и CI публикует образы + deploy-bundle в Forgejo.
Для **нового** prod-сервера с нуля используйте [`deploy.md`](./deploy.md) — там
Forgejo-источник с самого начала, этот документ не нужен.

## Суть и главная засада

На «старом» проде стоит **прежний `setup.sh`**, который умеет только GitHub
(заблокирован). Поэтому штатное авто-обновление (`setup.sh` → п.6) **не сработает** —
старый скрипт полезет качать bundle с GitHub. Сначала нужно **вручную** притащить
новый `setup.sh` через готовый bundle из Forgejo Release. После этого всё дальнейшее
— через новый `setup.sh` автоматически.

Дополнительно меняется источник образов: `ghcr.io/veryshuu/*` → `forgejo.mage.ru/mage/*`.
Registry приватный → для pull и скачивания bundle нужен токен.

**Будет downtime** (~10–15 мин на пересоздание контейнеров). Проводить в окно
обслуживания.

---

## Фаза 0. Подготовить deploy-токен (Forgejo UI)

На любой машине с доступом к `forgejo.mage.ru`:

1. Войти под аккаунтом (например `reydan`, либо заведите сервисный `portal-deploy`).
2. **Profile → Settings → Applications → Manage Access Tokens → Generate New Token**.
3. Имя: `portal-prod-deploy`. Scopes: **`read:package`** + **`read:repository`**
   (прод только тянет, писать не нужно).
4. **Сохранить значение токена** — показывается один раз. Записать также **username**
   владельца (= `FORGEJO_USER`).

> Токен даёт доступ к pull образов и скачиванию bundle. Для intranet/VPN-only
> портала этого достаточно.

---

## Фаза 1. Бэкап (на проде, до всего)

```bash
cd /opt/portal                          # ← ваш каталог прода (тут и далее)

# 1а. Дамп БД (обязательно — новая версия может накатить alembic-миграции)
docker compose exec -T postgres pg_dump -U portal portal > backup-pre-forgejo-$(date +%F).sql
ls -lh backup-pre-forgejo-*.sql         # убедиться, что файл не пустой

# 1б. Снапшот текущей конфигурации
cp .env               .env.bak-pre-forgejo-$(date +%F)
cp docker-compose.yml docker-compose.yml.bak-pre-forgejo-$(date +%F)
cp setup.sh           setup.sh.bak-pre-forgejo-$(date +%F)

# 1в. Зафиксировать, что крутится сейчас (для отката)
grep -E 'IMAGE_PREFIX|IMAGE_TAG' .env   # запомнить текущие значения
docker images | grep -E 'portal|ghcr'   # увидеть старые образы в кэше
```

⚠️ **Не делайте `docker image prune`** до конца миграции — старые `ghcr.io/*` образы
нужны для отката (GitHub заблокирован, перекачать их нельзя).

---

## Фаза 2. Bootstrap нового `setup.sh` (ручной, один раз)

Подставьте свой токен и username из Фазы 0:

```bash
# 2а. Скачать bundle v1.8.0 из Forgejo (репо приватный → токен в Authorization)
export FORGEJO_USER='reydan'            # ← ваш username из Фазы 0
export FORGEJO_TOKEN=' paste-token-here '

curl -fSL -H "Authorization: token ${FORGEJO_TOKEN}" \
  -o portal-deploy-bundle-v1.8.0.tar.gz \
  https://forgejo.mage.ru/mage/portal/releases/download/v1.8.0/portal-deploy-bundle-v1.8.0.tar.gz

ls -lh portal-deploy-bundle-v1.8.0.tar.gz   # ~86 КБ

# 2б. Распаковать (внутри: portal-deploy/{docker-compose.yml,setup.sh,.env.example,monitoring/})
tar xzf portal-deploy-bundle-v1.8.0.tar.gz

# 2в. Применить поверх текущего каталога (.env НЕ затрагивается — только
#     docker-compose.yml/setup.sh/.env.example/monitoring; старые .bak уже есть из Фазы 1)
cp portal-deploy/docker-compose.yml ./docker-compose.yml
cp portal-deploy/setup.sh           ./setup.sh
cp portal-deploy/.env.example       ./.env.example
rm -rf monitoring && cp -r portal-deploy/monitoring ./monitoring
chmod +x setup.sh

# 2г. Проверить, что новый setup.sh на месте
grep -c 'forgejo_docker_login\|FORGEJO_TOKEN' setup.sh   # должно быть > 0
```

Теперь на проде **новый `setup.sh`** (умеет Forgejo).

> Версия тега в URL (`v1.8.0`) — это та, на которую переходит прод. Для следующих
> релизов подставьте актуальный тег (список: `https://forgejo.mage.ru/mage/portal/releases`).

---

## Фаза 3. Поправить `.env`

Открыть `.env` и выставить 4 значения (`IMAGE_PREFIX`/`IMAGE_TAG` — заменить старые
строки; `FORGEJO_*` — добавить):

```bash
# было:  IMAGE_PREFIX=ghcr.io/veryshuu/
IMAGE_PREFIX=forgejo.mage.ru/mage/

# было:  IMAGE_TAG=v1.7.x   (или latest)
IMAGE_TAG=v1.8.0

# добавить (новые):
FORGEJO_USER=reydan                  # username владельца токена (Фаза 0)
FORGEJO_TOKEN= paste-token-here      # значение PAT из Фазы 0
```

Проверить:

```bash
grep -E 'IMAGE_PREFIX|IMAGE_TAG|FORGEJO_' .env
cat .portal-profile                   # должно быть "prod"
```

---

## Фаза 4. Переключение (pull + рестарт)

```bash
./setup.sh
```

В меню выбрать **`4` — «Полный рестарт с очисткой и запуск текущего режима»**.

Что произойдёт (автоматически):

- `preflight prod` — проверит semver-lock (`v1.8.0` ✓), непустой `IMAGE_PREFIX` ✓;
- **`forgejo_docker_login`** — `docker login forgejo.mage.ru` по
  `FORGEJO_USER`/`FORGEJO_TOKEN` из `.env`;
- `docker manifest inspect forgejo.mage.ru/mage/portal-backend:v1.8.0` — проверка
  существования тега в registry;
- `docker compose pull` — тянет все образы
  (`portal-backend/frontend/nginx/nginx-config/screenshot:v1.8.0` + `portal-postgres:16`);
- пересоздание контейнеров; backend на старте **сам накатит alembic-миграции**
  (смотрите лог: `docker compose logs -f backend`).

> **Альтернатива:** **п.6 «Обновить Production»** — тот же эффект + он ещё раз скачает
> и применит bundle (избыточно после Фазы 2, но канонический путь). Для **всех будущих**
> обновлений используйте именно п.6 — он сам тянет свежий bundle и образы из Forgejo,
> ручной bootstrap больше не нужен.

---

## Фаза 5. Проверка

```bash
# 5а. Healthcheck
curl -fsS http://localhost/ready && echo " ✓ /ready OK" || echo " ✗ /ready FAIL"

# 5б. Контейнеры живы, образы — из Forgejo
docker compose ps
docker compose images | grep -E 'forgejo.mage.ru|v1.8.0'

# 5в. Логи backend — миграции прошли без ошибок, startup complete
docker compose logs backend | grep -iE 'alembic|migrat|startup complete|error' | tail -20

# 5г. Smoke: открыть портал в браузере, логин, пройти по основным модулям
```

Если всё зелёное — **миграция завершена**. Прибраться:

```bash
rm -rf portal-deploy portal-deploy-bundle-v1.8.0.tar.gz
# старые ghcr-образы удалять только после 1–2 дней стабильной работы
```

---

## Фаза 6. Откат (если что-то сломалось)

```bash
# 6а. Вернуть .env и конфиги
cp .env.bak-pre-forgejo-$(date +%F)               .env
cp docker-compose.yml.bak-pre-forgejo-$(date +%F) docker-compose.yml
cp setup.sh.bak-pre-forgejo-$(date +%F)           setup.sh

# 6б. Поднять старый стек (образы ghcr.io/* ещё в кэше — НЕ пруненные)
docker compose up -d

# 6в. Если миграции новой версии успели накатиться и ломают совместимость со старым
#     кодом — восстановить БД из дампа Фазы 1:
docker compose exec -T postgres psql -U portal portal < backup-pre-forgejo-YYYY-MM-DD.sql
```

⚠️ Откат по БД — крайняя мера (теряются данные, накопленные после дампа). Сначала
смотрите логи — чаще проблема решается без отката.

---

## Шпаргалка по `.env`

| Переменная | Было (GHCR) | Стало (Forgejo) |
|---|---|---|
| `IMAGE_PREFIX` | `ghcr.io/veryshuu/` | `forgejo.mage.ru/mage/` |
| `IMAGE_TAG` | `v1.7.x` / `latest` | `v1.8.0` (релизный) |
| `FORGEJO_USER` | *(нет)* | username владельца PAT |
| `FORGEJO_TOKEN` | *(нет)* | PAT (`read:package` + `read:repository`) |

## После миграции — что изменилось навсегда

- На проде стоит **новый `setup.sh`** → все будущие обновления идут через Forgejo
  автоматически: `./setup.sh` → п.6 «Обновить Production». Сам скачает свежий bundle,
  залогинится в registry, спуллит образы, рестартнёт. Никакого GitHub.
- Перед следующим релизом меняется `IMAGE_TAG=v1.x.x` в `.env` (или `setup.sh` п.6
  предложит bump, если найдёт релиз новее текущего — semver-lock, ADR-047).
- `FORGEJO_USER`/`FORGEJO_TOKEN` в `.env` — теперь постоянные жители прода. Если токен
  когда-то отозвать — прод перестанет pull'ить.
