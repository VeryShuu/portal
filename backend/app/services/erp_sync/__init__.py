"""ERP-sync business services (docs/wip/erp-sync.md).

Импорт даты рождения и пола сотрудников из ERP-выгрузки (1С). Структура:

* :mod:`parser` — мульти-форматный парсер вложения (txt/csv/xlsx/xls) +
  авто-кодировка + дедуп дублей + детект конфликтов.
* :mod:`matcher` — оркестрация FIO-матчинга поверх ``users_repo``.
* :mod:`report` — HTML-отчёт админу (changed/unmatched/ambiguous/conflicts/errors).
* :mod:`importer` — основная транзакция: parse → match → update → diff → report.
* :mod:`mailbox` — IMAP-poll + post-fetch фильтрация писем.
* :mod:`recipients` — список адресов админов для уведомлений.
"""
