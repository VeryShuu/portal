"""Сертификаты о прохождении курса (этап 2; ТЗ §15).

Триггер — завершение курса: сертификат генерируется лениво при первом
запросе участника после полного прохождения (без cron и без нагрузочного
хвоста на эндпоинтах прохождения). PDF рендерится существующим
screenshot-service (``app.core.pdf.render_pdf``), хранится локально в
``/data/learning/certificates/<course_id>/<certificate_id>.pdf`` — третий
легитимный локальный корень модуля. Повторные запросы отдают сохранённый
файл: серийный номер и дата выдачи неизменны.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from html import escape
from pathlib import Path
from urllib.parse import quote

from fastapi import HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.learning import LearningCertificate, LearningCourse
from app.services.learning import courses_service as cs
from app.services.learning.participant import LearningParticipant

logger = get_logger(__name__)


def certificates_dir() -> Path:
    return Path(cs.LEARNING_DATA_DIR) / "certificates"


def certificate_pdf_path(course_id: uuid.UUID, certificate_id: uuid.UUID) -> Path:
    return certificates_dir() / str(course_id) / f"{certificate_id}.pdf"


def resolve_certificate_path(cert: LearningCertificate) -> Path | None:
    """Канонический путь или None (та же страховка от подмены пути в БД)."""
    expected = certificate_pdf_path(cert.course_id, cert.id)
    path = Path(cert.pdf_path)
    if path != expected or not path.is_file():
        return None
    return path


async def get_certificate(
    db: AsyncSession, course_id: uuid.UUID, participant: LearningParticipant
) -> LearningCertificate | None:
    if participant.user_id is not None:
        principal_column = LearningCertificate.user_id
        principal_id: uuid.UUID | None = participant.user_id
    else:
        principal_column = LearningCertificate.learning_account_id
        principal_id = participant.learning_account_id
    res = await db.execute(
        select(LearningCertificate).where(
            LearningCertificate.course_id == course_id,
            principal_column == principal_id,
        )
    )
    return res.scalar_one_or_none()


def certificate_html(
    *,
    serial: str,
    participant_name: str,
    course_title: str,
    issued_at: datetime,
) -> str:
    """HTML-шаблон листа A4; все интерполированные значения экранированы."""
    date_text = issued_at.strftime("%d.%m.%Y")
    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<style>
  @page {{ size: A4; margin: 0; }}
  body {{
    font-family: Georgia, "Times New Roman", serif;
    margin: 0;
    color: #1f2430;
  }}
  .frame {{
    box-sizing: border-box;
    width: 210mm;
    height: 297mm;
    padding: 18mm;
  }}
  .border {{
    box-sizing: border-box;
    height: 100%;
    border: 3px double #2c4a7c;
    padding: 24mm 20mm;
    text-align: center;
  }}
  .title {{
    font-size: 34pt;
    letter-spacing: 4px;
    text-transform: uppercase;
    margin: 18mm 0 4mm;
  }}
  .granted {{
    font-size: 13pt;
    color: #5a6272;
    margin-bottom: 14mm;
  }}
  .name {{
    font-size: 24pt;
    font-style: italic;
    margin-bottom: 6mm;
  }}
  .rule {{
    width: 90mm;
    border: 0;
    border-top: 1px solid #9aa3b5;
    margin: 6mm auto 4mm;
  }}
  .course {{
    font-size: 16pt;
    font-weight: bold;
    margin-bottom: 16mm;
  }}
  .footer {{
    margin-top: 22mm;
    font-size: 11pt;
    color: #5a6272;
  }}
  .serial {{
    font-size: 11pt;
    color: #5a6272;
    margin-top: 3mm;
    letter-spacing: 1px;
  }}
</style>
</head>
<body>
  <div class="frame"><div class="border">
    <div class="title">Сертификат</div>
    <div class="granted">настоящим подтверждает прохождение курса</div>
    <div class="name">{escape(participant_name)}</div>
    <hr class="rule">
    <div class="course">«{escape(course_title)}»</div>
    <div class="footer">Дата выдачи: {escape(date_text)}</div>
    <div class="serial">№ {escape(serial)}</div>
  </div></div>
</body>
</html>"""


def _serial() -> str:
    """Короткий номер документа: 8 символов без неоднозначных (0/O, 1/I)."""
    alphabet = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
    import secrets

    return "LC-" + "".join(secrets.choice(alphabet) for _ in range(8))


async def ensure_certificate(
    db: AsyncSession,
    course: LearningCourse,
    participant: LearningParticipant,
    *,
    items: list[cs.MyCourseItem],
) -> tuple[LearningCertificate, bool]:
    """Выдать сертификат за завершённый курс (или вернуть существующий).

    Возвращает ``(сертификат, только_что_выдан)``. Порядок выдачи:
    1) перечитали «уже выдан»; 2) отрендерили PDF; 3) вставили строку ОДНИМ
    flush'ом — UUID и канонический pdf_path известны до вставки, «заготовка»
    с пустым путём и второй flush не нужны (ревью 2026-08-30: уникальный
    индекс срабатывал на первом flush, а IntegrityError ловили на втором →
    реальная гонка завершалась 500); 4) записали файл; commit делает роутер.
    Рендер сознательно идёт ВНУТРИ транзакции: rollback перед ним экспайрит
    ORM-объекты курса и ломает sync-доступ в роутере (MissingGreenlet) —
    редкость выдачи делает удержание соединения приемлемым.
    Гонка двух параллельных первых запросов закрывается частичными уникальными
    индексами: проигравший откатывает свой savepoint и перечитывает победителя
    с ограниченным ретраем — победитель мог ещё не закоммитить вставку.
    ``items`` — уже проверенные элементы курса с флагами завершённости
    (результат ``courses_service.course_for_participant``)."""
    existing = await get_certificate(db, course.id, participant)
    if existing is not None:
        return existing, False

    if not items or not all(i.completed for i in items):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Сертификат недоступен")

    issued_at = datetime.now(UTC)
    cert: LearningCertificate | None = None
    pdf = b""
    try:
        from app.core.pdf import render_pdf

        for _attempt in range(3):
            serial = _serial()
            pdf = await render_pdf(
                certificate_html(
                    serial=serial,
                    participant_name=participant.display_name or "Обучаемый",
                    course_title=course.title,
                    issued_at=issued_at,
                )
            )
            candidate = LearningCertificate(
                id=uuid.uuid4(),
                course_id=course.id,
                user_id=participant.user_id,
                learning_account_id=participant.learning_account_id,
                serial=serial,
                pdf_path=str(certificate_pdf_path(course.id, uuid.uuid4())),
                issued_at=issued_at,
            )
            # Путь каноничен относительно собственного id — фиксируем до вставки.
            candidate.pdf_path = str(certificate_pdf_path(course.id, candidate.id))
            try:
                async with db.begin_nested():
                    db.add(candidate)
                    await db.flush()
            except IntegrityError:
                # Параллельный запрос выдал сертификат первым — отдаём его.
                winner = await get_certificate(db, course.id, participant)
                if winner is not None:
                    return winner, False
                # Победитель ещё не закоммитил — ограниченное перечитывание.
                await asyncio.sleep(0.2)
                continue
            cert = candidate
            break
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning(
            "learning.certificate_render_failed", course_id=str(course.id), error=str(exc)
        )
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Сервис подготовки PDF временно недоступен, попробуйте позже",
        ) from exc

    if cert is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, detail="Не удалось выдать сертификат"
        )

    dest = Path(cert.pdf_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    from aiofiles import open as aio_open

    async with aio_open(dest, "wb") as f:
        await f.write(pdf)
    # На crash между файлом и commit'ом роутера в /data остаётся осиротевший
    # PDF — без строки в БД он недоступен по API; приемлемая цена за отказ
    # от второго flush (ревью 2026-08-30).
    logger.info(
        "learning.certificate_issued",
        course_id=str(course.id),
        certificate_id=str(cert.id),
        kind=participant.kind,
    )
    return cert, True


async def file_response(cert: LearningCertificate) -> StreamingResponse:
    """Раздача PDF стримингом (прецедент материалов модуля)."""
    path = resolve_certificate_path(cert)
    if path is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Файл сертификата не найден")

    async def chunk_iter() -> AsyncIterator[bytes]:
        import aiofiles

        async with aiofiles.open(path, "rb") as f:
            while True:
                chunk = await f.read(1024 * 1024)
                if not chunk:
                    break
                yield chunk

    return StreamingResponse(
        chunk_iter(),
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f"attachment; filename*=UTF-8''{quote(f'certificate-{cert.serial}.pdf')}"
            ),
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
