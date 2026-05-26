"""Обработка загруженных фото: thumbnails, EXIF, detect-missing re-queue."""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, or_, select, update

from app.core.database import AsyncSessionLocal
from app.core.logging import get_logger
from app.models.photos import Photo, PhotoFolder
from app.services import photos_storage
from app.services.photos_realtime import publish_photo_processed

logger = get_logger(__name__)


async def process_photo_upload(ctx: dict, photo_id: str) -> None:
    """Thumbnails + EXIF + blurhash; атомарно отмечает processed и публикует SSE."""
    pid = uuid.UUID(photo_id)

    # Redis-lock защищает от параллельной обработки одного и того же фото
    # несколькими job'ами (cron requeue + первичный upload могут пересечься).
    # TTL короткий: внутренний код идемпотентен (skip если 200.webp есть), поэтому
    # «лишнее» исполнение безвредно, зато orphan-локи от убитых воркеров не
    # блокируют ретраи дольше пары минут.
    pool = ctx.get("redis")
    lock_key = f"photos:proc-lock:{pid}"
    lock_acquired = False
    if pool is not None:
        try:
            lock_acquired = bool(await pool.set(lock_key, "1", ex=120, nx=True))
            if not lock_acquired:
                logger.info("photos.process.skip_locked", photo_id=photo_id)
                return
        except Exception:
            lock_acquired = False

    try:
        await _process_photo_upload_inner(ctx, pid, photo_id)
    except BaseException as exc:
        # Без top-level логирования любой raise в inner превращается в
        # бесконечный цикл retry без диагностики (включая asyncio.CancelledError,
        # которое НЕ ловится `except Exception` и приводит к молчаливым tries).
        # Логируем + проглатываем (исключение — отмену, её надо пробросить).
        logger.exception(
            "photos.process.unhandled_error",
            photo_id=photo_id,
            error=str(exc),
            error_type=type(exc).__name__,
        )
        # CancelledError всегда пробрасываем — иначе ломаем shutdown
        import asyncio as _asyncio

        if isinstance(exc, _asyncio.CancelledError):
            raise
    finally:
        if lock_acquired and pool is not None:
            with contextlib.suppress(Exception):
                await pool.delete(lock_key)


async def _process_photo_upload_inner(ctx: dict, pid: uuid.UUID, photo_id: str) -> None:
    async with AsyncSessionLocal() as db:
        res = await db.execute(select(Photo).where(Photo.id == pid))
        photo = res.scalar_one_or_none()
        if not photo or photo.deleted_at is not None:
            return

        thumb_dir = photos_storage.THUMBS_ROOT / str(pid)
        thumb_200 = thumb_dir / "200.webp"
        thumbs_exist = await asyncio.to_thread(thumb_200.exists)

        if getattr(photo, "processed", False) and thumbs_exist and photo.blurhash:
            logger.info("photos.process.already_processed", photo_id=photo_id)
            return

        folder_res = await db.execute(select(PhotoFolder).where(PhotoFolder.id == photo.folder_id))
        folder = folder_res.scalar_one_or_none()
        if not folder:
            return

        original_path = (
            photos_storage.folder_fs_path(folder.fs_path or folder.path) / photo.filename
        )
        original_exists = await asyncio.to_thread(original_path.exists)
        if not original_exists and not thumbs_exist:
            logger.warning(
                "photos.process.missing_original", photo_id=photo_id, path=str(original_path)
            )
            return

        thumb_ok = thumbs_exist
        if not thumbs_exist and original_exists:
            sem = photos_storage._get_thumb_semaphore()
            try:
                async with sem:
                    await asyncio.to_thread(photos_storage.generate_thumbnails, pid, original_path)
                thumb_ok = True
            except Exception as exc:
                logger.exception("photos.process.thumb_failed", photo_id=photo_id, error=str(exc))
                # Не блокируем UX: даже если thumb-генерация упала (битый файл,
                # формат не поддерживается, OOM-bomb), оригинал есть и API
                # отдаст его через original-fallback. Помечаем processed=true,
                # чтобы фронт убрал спиннер и SSE обновил карточку.
                thumb_ok = False

        blurhash_str: str | None = photo.blurhash
        if thumb_ok and not blurhash_str:
            try:
                loop = asyncio.get_running_loop()
                blurhash_str = await loop.run_in_executor(
                    None, photos_storage.compute_blurhash, thumb_200
                )
            except Exception as exc:
                logger.warning("photos.process.blurhash_failed", photo_id=photo_id, error=str(exc))

        need_exif = original_exists and (
            not photo.exif or photo.width is None or photo.height is None
        )
        exif: dict = {}
        size: tuple[int, int] | None = None
        taken_at_iso: str | None = None
        if need_exif:
            try:
                from app.core.modules_config import load_modules

                strip_gps = load_modules().photos.strip_gps
            except Exception:
                strip_gps = True
            try:
                exif, size, taken_at_iso = photos_storage.extract_exif(
                    original_path, strip_gps=strip_gps
                )
            except Exception as exc:
                logger.exception("photos.process.exif_failed", photo_id=photo_id, error=str(exc))

        # processed=True даже без thumb — фронт спрячет спиннер, а API будет
        # отдавать original вместо WebP через _original_fallback_response.
        values: dict = {"processed": True}
        if blurhash_str and blurhash_str != photo.blurhash:
            values["blurhash"] = blurhash_str
        if size:
            values["width"] = size[0]
            values["height"] = size[1]
        if exif:
            values["exif"] = exif
        if taken_at_iso:
            with contextlib.suppress(Exception):
                values["taken_at"] = datetime.fromisoformat(taken_at_iso)
        await db.execute(update(Photo).where(Photo.id == pid).values(**values))
        await db.commit()
        logger.info("photos.processed", photo_id=photo_id, thumb_ok=thumb_ok)

        # SSE публикуем всегда — фронт обновит карточку и снимет спиннер,
        # даже если thumb не сгенерирован (API отдаст оригинал-fallback).
        pool = ctx.get("redis")
        if pool is not None:
            with contextlib.suppress(Exception):
                await publish_photo_processed(
                    pool,
                    photo_id=pid,
                    folder_id=photo.folder_id,
                    blurhash=blurhash_str,
                )


async def detect_missing_thumbnails(ctx: dict) -> dict:
    """Reconciler состояния processed↔thumbnails.

    1) processed=false, но thumb 200.webp есть на диске → in-place heal (ставим processed=true).
    2) processed=true, но thumb пропал с диска → сбрасываем processed=false и реэнкьюим.
    3) processed=false, thumb отсутствует, created < cutoff → реэнкьюим.

    Дедуп: `_job_id` бакетируется по 5 минутам (совпадает с интервалом крона),
    поэтому повторные ранки не плодят дубликаты в очереди, но раз в бакет фото
    может быть повторно поставлено.
    """
    requeued = 0
    healed = 0
    max_enqueues_per_run = 50
    pool = ctx.get("redis")
    if pool is None:
        logger.warning("photos.detect_missing.no_redis_pool")
        return {"requeued": 0, "healed": 0}

    cutoff = datetime.now(UTC) - timedelta(minutes=2)
    # Если фото старше этого порога и thumb всё ещё не создан — считаем
    # картинку неконвертируемой (битый файл, decompression-bomb, неподдерживаемый
    # формат) и больше не реэнкьюим. UX покрыт original-fallback на API.
    give_up_cutoff = datetime.now(UTC) - timedelta(minutes=30)
    bucket = int(datetime.now(UTC).timestamp()) // 300

    async with AsyncSessionLocal() as db:
        batch_size = 500
        offset = 0
        while True:
            res = await db.execute(
                select(Photo)
                .where(
                    Photo.deleted_at.is_(None),
                    or_(
                        Photo.processed.is_(True),
                        and_(Photo.processed.is_(False), Photo.created_at < cutoff),
                    ),
                )
                .order_by(Photo.id)
                .limit(batch_size)
                .offset(offset)
            )
            photos_batch = res.scalars().all()
            if not photos_batch:
                break

            for photo in photos_batch:
                is_processed = getattr(photo, "processed", True)
                thumb = photos_storage.THUMBS_ROOT / str(photo.id) / "200.webp"
                thumb_exists = await asyncio.to_thread(thumb.exists)
                should_requeue = False

                if is_processed and not thumb_exists:
                    # «Сдаёмся» по старым фото: thumb не создаётся ни с какого
                    # числа попыток (битый файл / bomb / OOM). API отдаст
                    # оригинал — фронт всё равно покажет картинку.
                    if photo.created_at < give_up_cutoff:
                        continue
                    try:
                        await db.execute(
                            update(Photo).where(Photo.id == photo.id).values(processed=False)
                        )
                        await db.commit()
                    except Exception as _reset_exc:
                        logger.warning(
                            "photos.detect_missing.reset_failed",
                            photo_id=str(photo.id),
                            error=str(_reset_exc),
                        )
                    should_requeue = True
                elif not is_processed and thumb_exists:
                    try:
                        await db.execute(
                            update(Photo).where(Photo.id == photo.id).values(processed=True)
                        )
                        await db.commit()
                        healed += 1
                    except Exception as _heal_exc:
                        logger.warning(
                            "photos.detect_missing.heal_failed",
                            photo_id=str(photo.id),
                            error=str(_heal_exc),
                        )
                    if not photo.blurhash:
                        should_requeue = True
                elif not is_processed and not thumb_exists:
                    should_requeue = True

                if should_requeue and requeued < max_enqueues_per_run:
                    # Не реэнкьюим, если по фото уже идёт обработка (lock-key
                    # держится воркером): иначе очередь забивается duplicate-job'ами,
                    # которые внутри upload только заберут lock впустую.
                    try:
                        lock_held = await pool.exists(f"photos:proc-lock:{photo.id}")
                    except Exception:
                        lock_held = 0
                    if lock_held:
                        continue
                    try:
                        await pool.enqueue_job(
                            "process_photo_upload",
                            str(photo.id),
                            _job_id=f"photos:reprocess:{photo.id}:{bucket}",
                        )
                        requeued += 1
                    except Exception as exc:
                        logger.warning(
                            "photos.detect_missing.enqueue_failed",
                            photo_id=str(photo.id),
                            error=str(exc),
                        )

            if len(photos_batch) < batch_size:
                break
            offset += batch_size
    logger.info("photos.detect_missing.done", requeued=requeued, healed=healed)
    return {"requeued": requeued, "healed": healed}
