"""Клиент Matrix Client-Server API (Synapse) для персональных уведомлений.

Публичный API (зеркало :mod:`app.services.max_messenger`):
* :func:`whoami` — проверка access-токена (для тест-эндпоинта админки);
* :func:`send_message` — идемпотентная отправка ``m.room.message`` (txnId);
* :func:`create_dm` / :func:`get_direct_rooms` / :func:`set_direct_room` —
  персональные DM-комнаты и кэш ``m.direct``;
* :func:`matrix_id_for_user` — MXID-конвенция из email;
* :class:`MatrixApiError` + :func:`classify_http_error` — для outbox-воркера.
"""

from app.services.matrix_messenger._client import (
    MatrixApiError,
    classify_http_error,
    close_matrix_http_client,
    create_dm,
    get_direct_rooms,
    init_matrix_http_client,
    matrix_id_for_user,
    send_message,
    set_direct_room,
    whoami,
)
from app.services.matrix_messenger.dm import DmResolver

__all__ = [
    "DmResolver",
    "MatrixApiError",
    "classify_http_error",
    "close_matrix_http_client",
    "create_dm",
    "get_direct_rooms",
    "init_matrix_http_client",
    "matrix_id_for_user",
    "send_message",
    "set_direct_room",
    "whoami",
]
