"""Публичные мета-параметры модуля обучения.

``GET /learning/meta`` отдаёт origin'ы, iframe с которых разрешён
(runtime-настройка ``system.json → video_iframe_origins``). Нужен learn-
сборке (у неё нет портал-«/bootstrap») и гейту плеера материалов на обоих
контурах: парсер видео не должен предлагать embed, который CSP заблокирует.

Без аутентификации: данных о пользователе нет, список доменов не секрет;
эндпоинт закрыт гейтом модуля (выключен learning → 404) и попадает под
rate-зону ``learning`` на публичном контуре как остальной ``/api/v1/learning/*``.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import require_learning_module as _module_gate
from app.core.system_config import load_system_settings
from app.schemas.learning import LearningMetaOut

router = APIRouter(
    prefix="/learning",
    tags=["learning"],
    dependencies=[Depends(_module_gate)],
)


@router.get("/meta", response_model=LearningMetaOut)
async def get_learning_meta() -> LearningMetaOut:
    return LearningMetaOut(video_iframe_origins=list(load_system_settings().video_iframe_origins))
