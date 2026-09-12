# Forgejo Actions Runner — настройка для portal CI

> Контекст: миграция с GitHub Actions. После переезда репозитория в
> `forgejo.mage.ru/mage/portal` workflows (`.forgejo/workflows/`) исполняются
> **forgejo-runner**'ом. Runner — отдельный процесс, который опрашивает Forgejo
> на наличие задач и исполняет их через Docker. Без runner'а все workflows висят
> в `waiting`.

Ниже — **Вариант A (рекомендуется)**: runner контейнером рядом с forgejo
(если forgejo уже в Docker). **Вариант B** — бинарник на хосте (без docker у forgejo).

---

## Вариант A: runner как Docker-контейнер (forgejo в docker) ⭐

### Архитектура (почему именно так)

```
┌──────────────────── хост-сервер (Docker daemon) ────────────────────┐
│                                                                      │
│  docker-compose (твой):                                              │
│   ┌──────────────┐   ┌──────────────┐   ┌────────────────────────┐  │
│   │ forgejo      │   │ postgres     │   │ forgejo-runner          │  │
│   │ :3000 :222   │   │ (внутр. сеть)│   │ монтирует docker.sock   │  │
│   └──────────────┘   └──────────────┘   └────────────────────────┘  │
│                                                  │                   │
│                         runner через сокет создаёт JOB-контейнеры   │
│                                                  ▼                   │
│   ┌─────────────────────────────────────────────────────────────┐   │
│   │ JOB-контейнер (forgejo.mage.ru/mage/act-ubuntu:22.04)       │   │
│   │  • network: host  → localhost = хост (видит pg/redis job'а) │   │
│   │  • docker.sock    → docker build/run/compose = демон хоста  │   │
│   └─────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────┘
```

Это **ближайший аналог GitHub `ubuntu-latest`**: job-контейнер работает с демоном хоста
через сокет и видит `localhost` как хост. Поэтому workflows (с `docker run -p 5432` +
`DATABASE_URL=...localhost:5432`) исполняются без переделок.

> ⚠️ **Безопасность:** проброс `/var/run/docker.sock` даёт CI-задачам root-доступ к хосту.
> Для одиночного админ-инстанса (ты единственный пользователь) это допустимо. Для
> multi-user — используй DinD-вариант (см. конец): job-задачи изолированы в отдельном
> docker-демане и не могут тронуть контейнеры forgejo.

### Что нужно на сервере

- Docker + Docker Compose v2 (уже есть — forgejo крутится в docker)
- Доступ к интернету: runner тянет pip/npm-зависимости и тестовые образы
  (`redis:7`, базовый `postgres:16`). Базовый образ job'ов и security-тулзы
  (act-ubuntu/gitleaks/trivy/zaproxy) — зеркала в собственном registry
  `forgejo.mage.ru/mage/*` (см. §«Зеркало ghcr-образов в свой registry» ниже —
  ghcr.io с раннера недостижим, инцидент 2026-08-24).

### Шаг 1. Каталог + конфиг рядом с compose forgejo

```bash
# Перейди туда, где лежит твой docker-compose.yml (forgejo + postgres):
cd /opt/forgejo   # ← замени на свой путь

mkdir -p runner-data
cat > runner-data/runner-config.yml <<'YAML'
log:
  level: info

runner:
  # Service runner: integration/E2E/Compose/ZAP. Пока E2E и ZAP используют
  # host-порт 8000, capacity должен оставаться 1.
  capacity: 1
  timeout: 30m
  insecure: false
  # Service jobs требуют оба labels: ubuntu-latest и ci-services.
  labels:
    - "ubuntu-latest:docker://forgejo.mage.ru/mage/act-ubuntu:22.04@sha256:be3b065b90a7a029ea30aa8ce897a62bfc8bd4d6698951b2527e1f11ba70cc6c"
    - "ubuntu-22.04:docker://forgejo.mage.ru/mage/act-ubuntu:22.04"
    - "ci-services"

cache:
  enabled: true
  dir: /data/cache

container:
  # host-сеть: job-контейнер разделяет network-namespace ХОСТА →
  # postgres/redis, запущенные job'ом через `docker run -p 5432/6379`, видны по localhost.
  # Обязательна для service-job'ов (integration/e2e/compose-smoke).
  network: "host"
  valid_volumes:
    - '/var/run/docker.sock'
  docker_host: "unix:///var/run/docker.sock"
  # ⚠️ НЕ добавляй `-v /var/run/docker.sock` в options — runner монтирует сокет сам
  # (docker_host = unix-сокет). Явный mount → «Duplicate mount point» → create падает.
  # Здесь — только add-host: job-контейнеры не резолвят compose-имя `forgejo` (runner
  # зарегистрирован на http://forgejo:3000). host-сеть у job'ов → forgejo:127.0.0.1.
  options: "--add-host=forgejo:127.0.0.1"
YAML
```

### Шаг 2. Добавить сервис в docker-compose.yml

Допиши в свой существующий `docker-compose.yml` (рядом с `forgejo` и `postgres`)
новый сервис `forgejo-runner`:

```yaml
  forgejo-runner:
    image: data.forgejo.org/forgejo/runner:13
    container_name: forgejo-runner
    restart: unless-stopped
    depends_on:
      - forgejo
    # root: runner пишет .runner в /data + есть доступ к docker.sock. Безопасно —
    # сокет и так даёт host-root; не-root упадёт на «permission denied» при записи .runner.
    user: "0:0"
    volumes:
      - ./runner-data:/data
      - /var/run/docker.sock:/var/run/docker.sock
    # runner↔forgejo идёт по внутренней сети compose (http://forgejo:3000, без TLS).
    # Демон читает конфиг из /data/runner-config.yml (шаг 1).
    command: forgejo-runner daemon --config /data/runner-config.yml
```

### Шаг 3. Зарегистрировать runner (однократно)

Нужен registration-token (instance-scope). Получи его как админ:

```bash
curl -s -H "Authorization: token <ADMIN_TOKEN>" \
  https://forgejo.mage.ru/api/v1/admin/actions/runners/registration-token
# → {"token":"Q74G..."}   ← это REG_TOKEN

export REG_TOKEN='<вставь token из ответа>'
```

Регистрируем (one-shot — перезаписывает команду сервиса на `register`):

```bash
# ⚠️ Формат лейблов в v13 — ЧЕРЕЗ ДВОЕТОЧИЕ: «имя:schema://образ», НЕ через «=».
# Через «=» парсер режет по первому «:» и падает с «unsupported schema: //…».
docker compose run --rm forgejo-runner forgejo-runner register \
  --no-interactive \
  --instance http://forgejo:3000 \
  --token "$REG_TOKEN" \
  --name forgejo-runner-1 \
  --labels ubuntu-latest:docker://forgejo.mage.ru/mage/act-ubuntu:22.04@sha256:be3b065b90a7a029ea30aa8ce897a62bfc8bd4d6698951b2527e1f11ba70cc6c,ubuntu-22.04:docker://forgejo.mage.ru/mage/act-ubuntu:22.04,ci-services
```

> `register` в v13 помечен deprecated («declare connections in the runner
> configuration instead») — но **работает**. Предупреждение игнорируем. В будущих
> мажорных версиях runner'а может потребоваться config-based регистрация (instance
> URL + token в YAML/env вместо CLI-флага); пока — рабочий путь выше.

Команда создаст файл `runner-data/.runner` (учётка бегуна). Проверь:

```bash
ls -la runner-data/.runner   # должен существовать
```

### Шаг 4. Запустить демон

```bash
docker compose up -d forgejo-runner
docker compose logs -f forgejo-runner   # увидишь «runner started» / «polling»
```

### Шаг 5. Проверить

1. В UI: **Site Administration → Actions → Runners**
   (`https://forgejo.mage.ru/-/admin/actions/runners`) — бегун со статусом `idle`.
2. Реальный прогон: в `mage/portal` создай тестовый PR (или попроси толкнуть пустой
   коммит в ветку) — job должен уйти в `running`.

Логи конкретной задачи: **Actions → нужный run → job → шаги**.

## Два runner'а: быстрые проверки + service jobs

CI маршрутизирует обычные проверки на `ci-general`, а integration, E2E,
Compose smoke и nightly ZAP — на `ci-services`. Service runner остаётся в
`host` network с `capacity: 1`; второй runner поднят в bridge network.

**`capacity: 8` у general runner (поднято с 4, 2026-09-07).** Прогоны CI и
security приходят в очередь одного раннера одновременно (~25 job'ов на push в
main): при capacity 4 security-джобы (лёгкие, ~1 мин) ждали начала 8–20 минут
позади основного CI, и общий time-to-green растягивался до 35+ мин. 8 слотов
съедают очередь; ограничитель — CPU/RAM хоста: следи за load average и памятью
после первого дня (`free -h`, `uptime`), при нехватке откатывай на 6.

```yaml
  forgejo-runner-general:
    image: data.forgejo.org/forgejo/runner:13
    container_name: forgejo-runner-general
    restart: unless-stopped
    depends_on:
      - forgejo
    user: "0:0"
    volumes:
      - ./runner-general-data:/data
      - /var/run/docker.sock:/var/run/docker.sock
    command: forgejo-runner daemon --config /data/runner-config.yml
```

`runner-general-data/runner-config.yml`:

```yaml
log:
  level: info
runner:
  # Было 4: security.yml стоял в очереди 8-20 мин позади ci.yml (см. выше).
  # 8 - рабочий компромисс; при нехватке CPU/RAM хоста - 6.
  capacity: 8
  timeout: 30m
  insecure: false
  labels:
    - "ubuntu-latest:docker://forgejo.mage.ru/mage/act-ubuntu:22.04@sha256:be3b065b90a7a029ea30aa8ce897a62bfc8bd4d6698951b2527e1f11ba70cc6c"
    - "ci-general:docker://forgejo.mage.ru/mage/act-ubuntu:22.04"
cache:
  enabled: true
  dir: /data/cache
container:
  valid_volumes:
    - "/var/run/docker.sock"
  docker_host: "unix:///var/run/docker.sock"
  network: "bridge"
  options: "--add-host=forgejo:host-gateway"
```

Зарегистрируй второй runner отдельным UUID/token через **Actions → Runners**
в UI Forgejo, затем добавь connection в его `runner-config.yml`; пустой
`runner-general-data` приведёт к ошибке `0 server connections configured`.
Перед включением workflow проверь в UI, что service runner объявляет
`ubuntu-latest, ci-services`, а general runner — `ubuntu-latest, ci-general`.

### Если первый прогон падает

CI переведён **без живого прогона**, поэтому первый запуск — это валидация.

| Симптом | Причина | Фикс |
|---|---|---|
| job висит `waiting` | runner не зарегистрирован / лейбл не мэтчит | Runners в UI: есть `ubuntu-latest` и `idle`? `runner-data/.runner` существует? |
| `Cannot connect to the Docker daemon` | сокет не проброшен в job | `container.options` + `valid_volumes` содержат `/var/run/docker.sock`? сокет смонтирован в сервис `forgejo-runner`? |
| `Connection refused localhost:5432` | job-контейнер не в host-сети | `container.network: "host"` в `runner-config.yml`? |
| `actions/checkout not found` / ошибка fetch action | зеркало недоступно | проверь доступ сервера к `code.forgejo.org`; workflow использует полный URL `https://code.forgejo.org/actions/...` |
| `pull access denied` / `failed to resolve reference` для `mage/act-ubuntu` | раннер не залогинен в свой registry (пакеты приватные) либо DNS хоста не резолвит registry | `docker login forgejo.mage.ru` на хосте раннера (§«Зеркало ghcr-образов»); проверь `docker pull forgejo.mage.ru/mage/act-ubuntu:22.04` вручную |
| `docker push forgejo.mage.ru/...` 401/403 | у auto-`GITHUB_TOKEN` нет scope на packages | заведи repo/org secret `REGISTRY_TOKEN` (write:package) и используй его в `publish-images` |
| `error saving credentials: rename /root/.docker/config.json… device or resource busy` | в job-контейнер bind-mount'ом примонтирован **файл** `/root/.docker/config.json` (host-креды зеркал): `docker login` сохраняет креды atomic-rename поверх точки монтирования → EBUSY (инцидент run #879, 2026-08-25: publish ×6 упали после мёрджа #128) | фикс в ci.yml: job-локальный `DOCKER_CONFIG` с сид-копией host-конфига перед `docker login` (jobs `build-postgres` и `publish-images`). Если монтируешь креды на раннере — монтируй каталог `/root/.docker` целиком (rename внутри каталога работает), а не одиночный файл |

### Чистка диска на раннере: что НЕ удалять (урок 2026-09-07)

При освобождении места на хосте раннера легко снести кэши — и прогоны незаметно
замедляются в разы (джобы, которые при тёплом кэше идут 1–2 мин, с холодного —
до 18 мин, вся очередь за ними стоит):

- **`runner-data/` и `runner-*-data/` — не удалять и не очищать.** Внутри
  `…/cache/` живёт кэш `actions/cache`: pip-пакеты, npm-кэш, Playwright-браузеры.
  Потеря каталога = все джобы заново качают зависимости.
- **Docker-образы — прайнить выборочно**, не `docker system prune -a`:
  базовый образ job'ов (`act-ubuntu`), `gitleaks`, `trivy`, Playwright-образы
  тянутся с registry при каждом прогоне, если их снести (~30–60с × каждая джоба).
  Безопасный вариант: `docker image prune --filter "until=168h"` (образы старше
  недели). Конкретно занятое место смотреть `docker system df -v`.
- Контейнеры/вVolume **остановленных CI-job'ов** (метки `portal.ci.managed=true`,
  `portal-ci-*`) прайнить можно и нужно — это основной мусор после integration/E2E.

### Изоляция Python-пакетов в параллельных job (инцидент run #1591, 2026-09-08)

`setup-python` может вернуть интерпретатор из примонтированного
`/opt/hostedtoolcache`. Если несколько job одновременно выполняют `pip install -e`
прямо в этот интерпретатор, они конкурируют за общие `*.dist-info` и могут падать
на `INSTALLER`, `REQUESTED` и других metadata-файлах. Кэш загрузок pip при этом
можно разделять: конфликт возникает в каталоге установленных пакетов.

После каждого `setup-python` workflow создаёт job-локальный `.venv-actions` и
добавляет его `bin` в `GITHUB_PATH`. Все последующие `python`/`pip` должны работать
только в этом venv. Не устанавливай зависимости CI напрямую в Python из
`/opt/hostedtoolcache`; при добавлении нового Python-job сохраняй этот шаг.

### Альтернатива: DinD (изоляция CI от forgejo)

Если беспокоит, что CI-jobs шарят демон с forgejo — замени проброс сокета на отдельный
docker-in-docker (официальный паттерн Forgejo). Добавь сервис `docker-in-docker`
(`image: docker:dind`, `privileged: true`, `command: dockerd -H tcp://0.0.0.0:2375 --tls=false`),
у `forgejo-runner` выставь `environment: DOCKER_HOST: tcp://docker-in-docker:2375`
и **убери** монтирование `/var/run/docker.sock`. Минус: `network: host` в job'ах тогда
означает сеть DinD-контейнера (работает, но семантика `localhost` чуть иная — проверь
на первом прогоне).

---

## Зеркало ghcr-образов в свой registry (forgejo.mage.ru/mage/*)

**Почему.** Инцидент 2026-08-24 (прогоны #829-831): ночные воркфлоу
(nightly-flakes, nightly-security, security) упали разом за 0 секунд — DNS на хосте
раннера перестал резолвить `ghcr.io` (`lookup ghcr.io … server misbehaving` от
systemd-resolved), а локальный кэш образов был вычищен очередным
`docker system prune` (лечение переполнения диска раннера). ghcr.io —
инфраструктура GitHub, доступ к ней из сети офиса нестабилен и не должен быть
условием работоспособности CI. Все ghcr-зависимости переведены на зеркала в
собственный Forgejo Container Registry (тот же, куда CI публикует образы портала):

| Зеркало | Исходник | Где используется |
|---|---|---|
| `forgejo.mage.ru/mage/act-ubuntu:22.04@sha256:be3b065b…` | `ghcr.io/catthehacker/ubuntu:act-22.04` | базовый образ job'ов — labels раннеров (этот файл + `scripts/forgejo-runner-config.yaml`) |
| `forgejo.mage.ru/mage/gitleaks:v8.30.1@sha256:b109bc5f…` | `ghcr.io/gitleaks/gitleaks:v8.30.1` | ci.yml, security.yml (secrets-scan) |
| `forgejo.mage.ru/mage/trivy:0.72.0@sha256:c6e969c5…` | `ghcr.io/aquasecurity/trivy:0.72.0` | ci.yml, security.yml (trivy-fs / image-scan) |
| `forgejo.mage.ru/mage/zaproxy:stable-8d387b1a@sha256:c558ee87…` | `ghcr.io/zaproxy/zaproxy:stable@sha256:8d387b1a…` | nightly-security.yml, security/zap-scan.sh |

**Все ссылки на зеркала пинуются `@sha256:<digest>` (аудит-3)**: теги в собственном
registry мутабельны (CI-токен имеет packages:write), их перезапись — ошибкой
обслуживания или компрометацией — тихо подменяет сканер/базовый образ, и security-гейт
«не находит» проблем. Digest = иммутабельная ссылка; полный digest исходника для
zaproxy дополнительно зашит в тег зеркала (`stable-<первые 8 символов digest>`).

⚠️ **Vuln-DB для trivy НЕ зеркалируется сознательно**: trivy качает свежую базу в
рантайме (ghcr.io/mirror.gcr.io). Устаревшая статичная DB = ложный green
security-гейта. Если DB недостижима — job падает красным (fail-closed).

### Что нужно на раннерах (однократно)

Пакеты в registry приватные (анонимный pull → 401), а job-образы тянет host-dockerd.
На **хосте каждого раннера** (и service, и general):

```bash
docker login forgejo.mage.ru -u reydan --password-stdin <<< '<токен с read:package>'
docker pull forgejo.mage.ru/mage/act-ubuntu:22.04@sha256:be3b065b90a7a029ea30aa8ce897a62bfc8bd4d6698951b2527e1f11ba70cc6c   # проверка
```

Затем заменить labels в конфиге обоих раннеров на
`forgejo.mage.ru/mage/act-ubuntu:22.04@sha256:be3b065b…` (см. шаблоны выше) и
перезапустить раннеры (`docker compose restart forgejo-runner
forgejo-runner-general`). Пока на раннерах стоит старый label с ghcr.io — ЛЮБОЙ прогон
CI падает на старте job-контейнера (`failed to resolve reference "ghcr.io/…"`).

### Обновление зеркал (по мере выхода версий upstream)

Выполняется с машины, где ghcr.io доступен (dev-WSL), после `docker login forgejo.mage.ru`:

```bash
docker pull ghcr.io/gitleaks/gitleaks:v8.31.0
docker tag  ghcr.io/gitleaks/gitleaks:v8.31.0 forgejo.mage.ru/mage/gitleaks:v8.31.0
docker push forgejo.mage.ru/mage/gitleaks:v8.31.0
# узнать digest залитого зеркала:
curl -s -u reydan:<PAT> -o /dev/null -D - \
  -H "Accept: application/vnd.docker.distribution.manifest.v2+json" \
  https://forgejo.mage.ru/v2/mage/gitleaks/manifests/v8.31.0 | grep -i docker-content-digest
# затем поднять версию И digest в .forgejo/workflows/ci.yml + security.yml
```

Для zaproxy — сначала узнать новый digest `:stable` через ghcr-API (инструкция в
комментарии nightly-security.yml), затем пере-зеркалировать с тегом
`stable-<digest8>`, узнать digest зеркала (как выше) и обновить ссылку
`тег@sha256:…` в воркфлоу и `security/zap-scan.sh`. Обновление act-ubuntu —
дополнительно поменять digest в labels конфигов ОБОИХ раннеров и перезапустить их.

---

## Вариант B: runner бинарником на хосте (systemd)

Если forgejo НЕ в docker или хочешь runner отдельным процессом. Скрипты:
`scripts/forgejo-runner-install.sh` + `scripts/forgejo-runner-config.yaml`. Запуск:

```bash
export FORGEJO_RUNNER_TOKEN='<REGISTRATION_TOKEN>'
sudo cp scripts/forgejo-runner-config.yaml /etc/forgejo-runner/config.yaml
sudo -E bash scripts/forgejo-runner-install.sh
```

Логика конфига та же (host-сеть + сокет), только пути хостовые (`/var/lib/forgejo-runner/`).
systemd-unit создаётся скриптом (`forgejo-runner.service`).
