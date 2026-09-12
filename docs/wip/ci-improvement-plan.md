# План доведения CI Portal до целевого состояния

> Когда читать: реализация улучшений CI, критерии приёмки, handoff.
> Основание: [аудит 2026-09-05](ci-audit-20260905.md), baseline `fe49d934`.
> Статус: план выполняется; PR #220 и #222 merged, один ручной nightly 5/5 успешно подтверждён. Долгосрочное наблюдение, runner RCA и полный внешний publication barrier ещё не закрыты.
> Принцип: небольшие PR, сохранение required contexts, проверка до/после; merge и release — решение пользователя.

## Цель и метрики

Сделать результаты воспроизводимыми, failures объяснимыми, релиз полностью закреплённым, а время обратной связи предсказуемым. Не сокращать реальные проверки под видом ускорения.

Предлагаемые цели принимаются после baseline-этапа и пилота; это критерии направления, не обещание уже измеренного ускорения:

| Показатель | Baseline | Целевое состояние |
|---|---|---|
| Успешный PR created→ready | p50 30:35 / sample p95 42:04, n=13 | первый этап p50 <=20 min, p95 <=25 min; затем оценить p50 <=15 min |
| Очередь ready→start | пока не отделена от needs | p95 <=2 min в согласованной рабочей нагрузке |
| Infrastructure failures | подтверждены минимум два Docker API failure | <1% за скользящие 30 дней; для приёмки пилота 0/20 |
| Nightly | два последних 5/5 collection failures | 7 последовательных ночей с полным выполнением, 0 неожиданных skips |
| Flakes | E2E до 2 допускаются, observed 1; backend без общего бюджета | сохранены все attempts; нет неизвестных flaky tests; владелец и срок <=7 дней |
| Publication | неполный barrier, mutable PostgreSQL | все policy gates того же SHA; manifest с digest каждого образа |
| Reproducibility | плавающий Python/tooling | одинаковые lock/tool versions и комплект digest для повторного запуска |
| Diagnostics | логи без единой истории | классификация infra/collection/product/flake, машинные отчёты и сроки хранения |

SLO рассчитывать отдельно для PR/main/release/nightly; тёплый/холодный cache и конкурентную нагрузку не смешивать. Ошибочные/отменённые runs показывать отдельным рядом, не удалять из reliability-статистики. p95 на 13 точках не считать надёжным долгосрочным прогнозом.

## Журнал реализации

| Дата | PR / commit | Сделано | Остаточный риск |
|---|---|---|---|
| 2026-09-05 | [#220](https://forgejo.mage.ru/mage/portal/pulls/220) / `73e0abea` | AnyIO ограничен ниже 4.15, nightly получает run-scoped PostgreSQL image, Knip закреплён и стал fail-closed для ошибок запуска/конфига. | Merged; ручной nightly API 1493 (UI 1491) — 5/5 success. Остаются 7 ночей и Docker RCA. |
| 2026-09-05 | [#222](https://forgejo.mage.ru/mage/portal/pulls/222) / `87505634` | `db-schema-drift` добавлен в `publish-images.needs`; exact same-workflow inventory защищён fail-closed Bats counterexamples. | External security results не входят в same-SHA publication barrier; manifest/digest promotion не реализован. |

## Этап 0. Зафиксировать baseline и среду

**Закрывает:** CI-02, CI-09, CI-16, CI-17. **Объём:** один небольшой tooling/docs PR и read-only инфраструктурная проверка. **Зависимости:** нет.

- [ ] Сохранить 20–30 сопоставимых прогонов; отдельные job/step timestamps, очередь после завершения needs, cache hit/miss, test attempts, версии.
- [ ] Проверить live runner config: capacity, labels→image digest, network, CPU/RAM quotas, disk free/inodes/I/O, Docker/runner versions, размещение daemon.
- [ ] Проверить credentials mounts и кто может запускать PR; значения секретов не сохранять.
- [ ] Получить Docker/runner logs и host telemetry вокруг failures 24055/24534; не приписывать timeouts ресурсам без данных.
- [ ] Зафиксировать точный список 22 required contexts и публикационных checks как машинный invariant.

**Gate:** собран безопасный evidence bundle; очереди отделены от выполнения; для каждого неизвестного — конкретный способ проверки и владелец. **Результат:** уточнённые SLO, перечень изменений раннеров для согласования.

## Этап 1. Восстановить работающие проверки

**Закрывает:** CI-01, CI-02, CI-03, CI-14. **Объём:** 2–3 независимых PR. **Приоритет:** первый.

- [x] Воспроизвести nightly collection error; исправить совместимость AnyIO/Starlette в контролируемом наборе версий. Не глушить все DeprecationWarning. PR #220: воспроизведение на AnyIO 4.15.0 и локальный collection после фикса.
- [x] Запустить 5 seeds с полным набором; summary показывает collection/infra failure отдельно от test failure. API 1493 (UI 1491), 2026-09-05: все 5 jobs success.
- [x] Настроить Knip entrypoints для portal/learn/E2E; проверить `auth.setup.ts` как используемый entrypoint. PR #220: `knip.json` включает E2E entrypoints и отключает загрузку credential-bound Playwright config.
- [x] Разделить informational dead-code findings и failure исполнения/конфигурации инструмента; поломка конфигурации обязана давать красный результат. PR #220: findings имеют `--no-exit-code`, ошибочный JSON возвращает код 2.
- [ ] Исправить подтверждённую причину Docker API failures из этапа 0; если RCA ещё нет, оставить пункт открытым.
- [ ] Добавить attempts/seed/outcome artifacts backend, не ослабляя skip gate. Разобрать E2E files-bulk retry и Vitest timeout на counterexample/ресурсных данных.

**Gate:** nightlies исполняются; поломка analyzer config выявляется; 20 сопоставимых CI без infrastructure failure, затем 7 ночей наблюдения. Факт «один зелёный запуск» недостаточен.

## Этап 2. Полная граница публикации и версии комплекта

**Закрывает:** CI-04, CI-05, CI-06. **Объём:** 2–3 PR, без автоматического релиза. **Можно проектировать параллельно этапу 1.**

- [x] Добавить db-schema gate в publication dependencies и invariant против будущего расхождения. PR #222 смёржен; exact inventory остальных same-workflow gates покрыт Bats counterexamples.
- [ ] Объединить required security результаты того же SHA с publication barrier; missing/cancelled result блокирует promotion.
- [ ] Собирать/сканировать по run-scoped immutable image identity; не сканировать shared `:16`.
- [ ] Формировать manifest из всех шести digest, source SHA, lock/toolchain, scan policy/version и build inputs.
- [ ] Закрепить PostgreSQL в deploy-bundle вместе с остальными образами; проверить совместимость setup/pull для текущего пользователя.
- [ ] Продвигать latest только для принятого main. Старый tag/RC не меняет latest.
- [ ] Разделить build/scan и promotion; публикацию полного набора сериализовать. Прерванная matrix не должна создавать «готовый» релиз.

**Gate:** контролируемые negative cases: каждый gate падает; результат отсутствует; scan CRITICAL; cancellation; два перекрывающихся runs; старый release/RC; повторный pull старого manifest. Ни один сценарий не должен выпустить непроверенный или смешанный комплект. Проверки выполнять в тестовом namespace, не на настоящих release tags.

**Откат:** вернуть pipeline через PR; сохранённые версии/digest не перезаписывать. Миграции БД не считать автоматически обратимыми.

## Этап 3. Воспроизводимая и быстрая подготовка окружения

**Закрывает:** CI-08, CI-11, CI-12. **Объём:** 2–3 PR. **Зависимости:** рабочие gates этапа 1.

- [ ] Единый Python lock/constraints для CI и production build; отдельная процедура планового обновления с тестами.
- [ ] Согласовать Node/npm с engine requirements, одинаковые версии для runner/Docker; запрещать необъяснённый EBADENGINE.
- [ ] Перенести Knip/jscpd из runtime npx install в закреплённые dev tools.
- [ ] Записать npm timing/debug и общие deadlines; найти причину 1000 s пауз.
- [ ] Пилот no-audit при установке зависимостей в несекьюрити jobs; explicit dependency audit остаётся required и блокирует публикацию.
- [ ] Подготовить runner image/wheelhouse с OS/browser prerequisites; version/digest и регулярное обновление. Не хранить небезопасный вечный cache окружения.

**Gate:** 5 повторов одного SHA на тёплом и минимум один на холодном cache; идентичные версии, полный security audit; нет install/Knip пауз > согласованного deadline. Выигрыш показывать отдельно для install и tests. Нет эффекта — изменение не принимать ради сложности.

## Этап 4. Убрать лишнюю работу, сохранив проверки

**Закрывает:** CI-12, CI-13. **Объём:** 2–3 небольших пилота. **Зависимости:** этап 3.

- [ ] Gitleaks: проверка диапазона коммитов, full-history fallback при любой неоднозначности; weekly/manual full scan сохраняется.
- [ ] Проверить секрет в промежуточном коммите, удалённый следующим; scanner обязан его обнаружить.
- [ ] Измерить повторные frontend builds/install; переиспользовать только artifact того же SHA с совпадающими build inputs и environment.
- [ ] Измерить postgres save/upload/load; не заменять корректный 35 s artifact flow на shared mutable image ради неподтверждённого выигрыша.
- [ ] Объединить setup лёгких drift checks только при сохранении exact required status contexts и диагностики каждого check.
- [ ] Для nightly подготовить immutable общий setup, сохранив пять независимых seeds.

**Gate:** сравнение 5 сопоставимых runs до/после, одинаковые pass/skip/security guarantees, средний и p95 эффект. Каждый cache проверяется на miss, stale input, смену lock/tool version. Не уменьшать tests/repeats, coverage threshold или количество security checks.

## Этап 5. Безопасно изменить параллелизм

**Закрывает:** CI-09, CI-10, часть CI-16. **Зависимости:** этапы 0–3; изоляция image tags обязательна до увеличения capacity.

- [ ] Уникальные tags/names/ports для nightly, Compose и всех testcontainers consumers; экспорт PORTAL_POSTGRES_IMAGE. Частично выполнено в PR #220: nightly migration tests получили run-scoped image; Compose и перекрывающиеся runs ещё не проверены.
- [ ] Устранить shared `:ci/:16` в тестовых jobs; cleanup строго своего scope.
- [ ] Проверить перекрытие двух run scopes, отмену одного и сохранность второго.
- [ ] Выбрать увеличение capacity, отдельный smoke runner или отдельный service host по CPU/RAM/I/O baseline.
- [ ] После этого убрать искусственные needs integration→E2E→smoke, сохранив зависимости на нужные артефакты и общий barrier.
- [ ] Ограничить pytest/Vitest/Playwright workers относительно реальной квоты job, а не количества CPU всего host.

**Gate:** два одновременных CI плюс nightly не смешивают данные/образы, не трогают чужие контейнеры; SLO улучшается без роста flaky/OOM/timeouts. **Откат:** вернуть capacity/dependencies; изоляцию и gates оставить.

## Этап 6. Проверять именно поставляемый продукт

**Закрывает:** CI-07, CI-15. **Объём:** отдельные интеграционные PR.

- [ ] Запускать точный candidate manifest на тестовом контуре, через реальный Nginx.
- [ ] Проверять portal/learn routing, public/internal allowlist, TLS, static assets и корректную работу после login.
- [ ] Проверять worker readiness и выполнение минимального задания с наблюдаемым результатом.
- [ ] Добавить auth ZAP для минимального набора ролей и отчёт operation/status coverage; число URL не заменяет прохождение auth.
- [ ] Полный vulnerability inventory, включая unfixed; отдельно policy blocking, исключения с владельцем/сроком.
- [ ] Пилот SAST с ограниченным набором релевантных правил; baseline findings и новые блокирующие регрессии различать.

**Gate:** counterexamples сломанного Nginx fallback/allowlist, отсутствующего worker, повреждённого manifest и недоступной auth operation приводят к ожидаемой ошибке. Checks не используют production data.

## Этап 7. Сопровождение без повторного накопления проблем

**Закрывает:** CI-17 и поддерживает все этапы.

- [ ] Автоматический job/required-context inventory и актуальное ручное описание гарантий в docs/testing.md.
- [ ] Сохранять p50/p95 queue/setup/tests, infra failure rate, rerun/skip counts, cache hit, версии и seed.
- [ ] Назначить владельца red nightly; collection/infra failure требует реакции в следующий рабочий день.
- [ ] Регулярно обновлять locks, scanner DB/tools и runner images; проверять холодный bootstrap.
- [ ] Ежемесячно сверять publication barrier и branch protection с inventory.

**Gate:** 30-дневный отчёт, устойчивые SLO и рабочий runbook. Наблюдение не автоматизировано этим аудитом; scheduled tasks не создавались.

## Порядок PR и оценка объёма

Ориентир — **10–15 небольших PR**, ориентировочно **2–4 недели инженерной работы** при доступе к инфраструктуре, плюс календарное наблюдение 7/30 дней. Это предварительная оценка, а не обещанный срок. Главные неопределённости: RCA Docker timeouts, устройство live runner host, совместимость полного manifest с текущим setup и длительность production-equivalent smoke.

Каждый PR: конкретная проблема → изменение → негативная проверка там, где нужен gate → сопоставимые timings → проверка required contexts. Для инфраструктуры сначала готовится reviewable конфигурация и способ отката. Не начинать с ускорения всех jobs одновременно.

## Handoff

СДЕЛАНО: read-only аудит baseline и реальных прогонов; 17 карточек проблем; нормализованные evidence; staged plan с gates и SLO; PR #220 подготовил первый узкий пакет CI-исправлений.

В РАБОТЕ: CI для exact inventory same-workflow publication gates; наблюдение 7 ночей после успешного ручного run 5/5. Live host capacity/resources/credential boundary и RCA Docker timeouts остаются незакрытыми проверками этапа 0.

ДАЛЕЕ: подтвердить CI для inventory gate; собирать 7 последовательных nightly; параллельно этап 0 — read-only inventory Docker/runner для RCA timeout. Затем проектировать same-SHA barrier для external security результатов отдельным PR.

ОТКРЫТЫЕ ВОПРОСЫ: доступ к runner host для telemetry; согласование SLO/ресурсов и политики HIGH/unfixed уязвимостей — перед соответствующим внедрением.

КОММИТ: документация должна идти отдельным docs-коммитом с тремя файлами аудита; не смешивать её с implementation PR. Предлагаемый текст: `docs(ci): record first reliability implementation`.
