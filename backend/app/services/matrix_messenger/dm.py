"""Резолв «MXID → DM-комната» через account data ``m.direct``.

Используется воркером messenger-outbox (батч-кэш на группу строк) и
тест-эндпоинтом админки. ``m.direct`` — стандартное хранилище DM-комнат
(его же ведут клиенты): бот видит и комнаты, созданные пользователем
вручную, поэтому не плодит дубликаты личных чатов.
"""

from __future__ import annotations

from app.core.logging import get_logger
from app.services.matrix_messenger._client import (
    create_dm,
    get_direct_rooms,
    set_direct_room,
)

logger = get_logger(__name__)


class DmResolver:
    """Кэш «MXID → room_id» поверх ``m.direct`` с ленивой загрузкой карты.

    Обновлённая карта пишется обратно best-effort: провал записи кэша не
    фейлит отправку — при следующем батче просто создастся новая комната
    (старая останется приглашённой, получатель её увидит).
    """

    def __init__(
        self,
        *,
        homeserver_url: str,
        access_token: str,
        bot_user_id: str,
    ) -> None:
        self._homeserver_url = homeserver_url
        self._access_token = access_token
        self._bot_user_id = bot_user_id
        self._direct_map: dict[str, list[str]] | None = None  # lazy load

    async def resolve(self, mxid: str) -> str:
        """Вернуть существующую DM-комнату или создать новую."""
        if self._direct_map is None:
            self._direct_map = await get_direct_rooms(
                homeserver_url=self._homeserver_url,
                access_token=self._access_token,
                bot_user_id=self._bot_user_id,
            )
        rooms = self._direct_map.get(mxid)
        if rooms:
            return rooms[0]

        room_id = await create_dm(
            homeserver_url=self._homeserver_url,
            access_token=self._access_token,
            invite_user_id=mxid,
        )
        self._direct_map[mxid] = [room_id]
        try:
            await set_direct_room(
                homeserver_url=self._homeserver_url,
                access_token=self._access_token,
                bot_user_id=self._bot_user_id,
                direct_map=self._direct_map,
            )
        except Exception as exc:
            logger.warning(
                "matrix_messenger.m_direct_update_failed",
                mxid=mxid,
                error=str(exc)[:300],
            )
        return room_id
