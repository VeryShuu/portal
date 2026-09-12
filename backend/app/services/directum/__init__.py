"""Бизнес-логика модуля Directum (docs/directum.md).

* :mod:`odata` — httpx-клиент OData (singleton, basic auth, системный trust store).
* :mod:`matcher` — триаж ФИО исполнителя → пользователь портала (реюз ``users_repo``).
* :mod:`digest` — текст дайджеста «просроченные задачи» для личного чата Matrix.
* :mod:`sync` — оркестрация прогона: fetch → матчинг → outbox (matrix + email) → run-строка.
* :mod:`report` — email-сводка прогона для админов.
* :mod:`recipients` — адресаты сводки (notify_emails или все админы).
"""
