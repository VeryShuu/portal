"""Генерация thumbnails фотогалереи (тяжёлый PIL + конкурентность).

Часть пакета :mod:`app.services.photos_storage` (см. его ``__init__``).

Патчабельные имена (``THUMBS_ROOT``, ``GENERATE_AVIF``, ``AVIF_MIN_SIZE``,
``_open_image``, ``generate_thumbnails``) читаются/вызываются через namespace
пакета (``from app.services import photos_storage as _ps``), чтобы
``patch("app.services.photos_storage.X", ...)`` из тестов действовал в runtime.
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_settings = get_settings()

THUMB_SIZES = (200, 400, 600, 1000, 1600)  # widget/grid (200–600), lightbox/preview (1000–1600)
THUMB_QUALITY = 85
# WebP encoder method: 0 — самый быстрый, 6 — самый «умный»/медленный.
# Снижено с 6 до 4: разница в размере файла <5%, скорость кодирования выше в 2–3 раза.
WEBP_METHOD = 4
# Опционально генерировать AVIF (дорогой кодек). Можно отключить через
# переменную окружения PHOTOS_GENERATE_AVIF=0, если CPU дорог (см. app.core.config).
GENERATE_AVIF = _settings.photos_generate_avif
# AVIF дорог; для сеточных миниатюр (200/400/600) выигрыш по размеру не оправдывает
# CPU. Генерируем AVIF только для больших размеров (lightbox/preview).
AVIF_MIN_SIZE = _settings.photos_avif_min_size

_MAX_IMAGE_PIXELS = 300_000_000  # ~300 MP, защита от OOM воркера при обработке гигантских файлов

_THUMB_GEN_LOCKS: dict[str, list] = {}
_THUMB_GEN_SEMAPHORE: asyncio.Semaphore | None = None
# Контейнер worker'а упирается в 2GB memory limit при concurrency=4 на
# крупных JPEG (5000×3000): один PIL Image в RAM ~ 60MB + каскад thumbnail'ов
# + pillow_heif → х4 параллельно = OOM kill (cgroup), который убивает arq
# вместе с in-flight задачами без шанса записать exception. Снижаем до 2
# (PHOTOS_THUMB_CONCURRENCY, см. app.core.config).
_THUMB_GEN_CONCURRENCY = _settings.photos_thumb_concurrency


def _get_thumb_semaphore() -> asyncio.Semaphore:
    global _THUMB_GEN_SEMAPHORE
    if _THUMB_GEN_SEMAPHORE is None:
        _THUMB_GEN_SEMAPHORE = asyncio.Semaphore(_THUMB_GEN_CONCURRENCY)
    return _THUMB_GEN_SEMAPHORE


def _import_pil(*, register_heif: bool = False) -> tuple[Any, Any]:
    """Централизованный lazy-import PIL для пакета thumbnails.

    Возвращает ``(Image, ImageOps)``. PIL — опциональная/тяжёлая зависимость,
    поэтому импортируется внутри функций (cold-start воркера, опц. кодеки).

    HEIF регистрируется только при ``register_heif=True`` — поведение 1:1 с
    прежним: ``register_heif_opener()`` вызывался исключительно в ``_open_image``.
    Ошибка регистрации HEIF (нет ``pillow_heif``) подавляется.
    """
    if register_heif:
        try:
            from pillow_heif import register_heif_opener

            register_heif_opener()
        except Exception:
            pass
    from PIL import Image, ImageOps

    return Image, ImageOps


async def generate_thumbnails_safe(photo_id: uuid.UUID, original_path: Path) -> dict[int, Path]:
    """Сериализованная on-the-fly генерация thumbnails.

    Защита от OOM при параллельных запросах: per-photo lock (dedupe) +
    глобальный семафор (cap по RAM). Если thumbnails уже сгенерированы
    к моменту попадания внутрь lock — возвращает пустой dict без работы.
    """
    from app.services import photos_storage as _ps

    key = str(photo_id)
    lock_info = _THUMB_GEN_LOCKS.get(key)
    if lock_info is None:
        lock = asyncio.Lock()
        _THUMB_GEN_LOCKS[key] = [lock, 1]
    else:
        lock = lock_info[0]
        lock_info[1] += 1

    try:
        async with lock:
            existing = _ps.THUMBS_ROOT / key
            if existing.exists() and all(
                (existing / f"{size}.webp").exists() for size in THUMB_SIZES
            ):
                return {}
            sem = _get_thumb_semaphore()
            async with sem:
                return await asyncio.to_thread(_ps.generate_thumbnails, photo_id, original_path)
    finally:
        lock_info = _THUMB_GEN_LOCKS.get(key)
        if lock_info is not None:
            lock_info[1] -= 1
            if lock_info[1] <= 0:
                _THUMB_GEN_LOCKS.pop(key, None)


def _open_image(path: Path, *, target_size: int | None = None) -> Any:
    Image, _ = _import_pil(register_heif=True)  # noqa: N806
    DecompressionBombError = Image.DecompressionBombError  # noqa: N806

    # Поднимаем PIL-лимит до нашего, чтобы Image.open не отказался от валидных
    # AI-апскейл картинок 200+ MP. От реального OOM защищаемся через draft()
    # (decoder-side downscale для JPEG, не аллоцирует полный bitmap).
    Image.MAX_IMAGE_PIXELS = _MAX_IMAGE_PIXELS
    img = Image.open(path)
    width, height = img.size
    if width * height > _MAX_IMAGE_PIXELS:
        raise DecompressionBombError(
            f"Image dimensions {width}x{height} exceed the limit of {_MAX_IMAGE_PIXELS} pixels"
        )
    if target_size is not None and target_size > 0:
        # JPEG draft() выбирает ближайший power-of-2 downscale внутри libjpeg,
        # снижая пиковую RAM в 4–64×. Для не-JPEG no-op. Зовём ДО load().
        with contextlib.suppress(Exception):
            img.draft("RGB", (target_size * 2, target_size * 2))
    try:
        img.load()
    except DecompressionBombError as e:
        logger.error("photos.decompression_bomb", path=str(path), error=str(e))
        raise
    return img


def _cascade_resize(current: Any, size: int) -> Any:
    """Один шаг каскадного downscale: вернуть bitmap с max-стороной ≤ ``size``.

    Если ``current`` уже не больше ``size`` — возвращает его как есть (без копии);
    иначе делает ``copy().thumbnail()`` (копия, чтобы не мутировать ``current``,
    который ещё нужен вызывающему для трекинга/очистки промежуточных bitmap'ов).
    """
    Image, _ = _import_pil()  # noqa: N806

    if max(current.size) > size:
        scaled = current.copy()
        scaled.thumbnail((size, size), Image.Resampling.LANCZOS)
        return scaled
    return current


def _encode_thumb(scaled: Any, out_dir: Path, size: int) -> Path:
    """Кодирует один thumbnail в WEBP (+AVIF для крупных размеров) и сохраняет.

    Возвращает путь к WEBP-файлу. AVIF-ветка дорогая и best-effort
    (ошибки кодека подавляются), генерируется только для ``size >= AVIF_MIN_SIZE``.
    """
    from app.services import photos_storage as _ps

    out_path = out_dir / f"{size}.webp"
    scaled.save(out_path, "WEBP", quality=THUMB_QUALITY, method=WEBP_METHOD)
    if _ps.GENERATE_AVIF and size >= _ps.AVIF_MIN_SIZE:
        avif_out = out_dir / f"{size}.avif"
        with contextlib.suppress(Exception):
            scaled.save(avif_out, "AVIF", quality=THUMB_QUALITY)
    return out_path


def generate_thumbnails(photo_id: uuid.UUID, original_path: Path) -> dict[int, Path]:
    """Генерирует thumbnails трёх размеров в WebP.

    Сохраняет в /data/photos/thumbs/{photo_id}/{size}.webp.
    Возвращает dict{size: path}.

    Все PIL-объекты явно закрываются через try/finally — без этого
    в гриде из 5–10 параллельных задач RSS контейнера легко уходит за
    2GB cgroup-лимит и worker OOM-killed (без шанса залогировать).
    """
    import gc

    _, ImageOps = _import_pil()  # noqa: N806

    from app.services import photos_storage as _ps

    out_dir = _ps.THUMBS_ROOT / str(photo_id)
    out_dir.mkdir(parents=True, exist_ok=True)

    img: Any = None
    transposed: Any = None
    converted: Any = None
    scaled: Any = None
    result: dict[int, Path] = {}
    intermediates: list[Any] = []
    try:
        # Передаём самый большой требуемый размер — JPEG-draft даунскейлит
        # на уровне декодера. Без этого 200+ MP картинка убивает воркер по OOM.
        img = _ps._open_image(original_path, target_size=max(THUMB_SIZES))
        transposed = ImageOps.exif_transpose(img)
        if transposed.mode not in ("RGB", "RGBA"):
            converted = transposed.convert("RGB")
            current = converted
        else:
            current = transposed

        # Каскадный downscale: сначала ужимаем оригинал до самого большого размера,
        # затем каждый следующий — из уже уменьшенного. На 5K×3K JPEG это даёт
        # 3–5× прирост скорости по сравнению с resize'ом оригинала на каждый размер.
        sizes_desc = sorted(THUMB_SIZES, reverse=True)
        for size in sizes_desc:
            scaled = _cascade_resize(current, size)
            result[size] = _encode_thumb(scaled, out_dir, size)
            # Освобождаем предыдущий промежуточный bitmap, текущий нужен
            # для следующей итерации downscale.
            if scaled is not current:
                intermediates.append(current)
            current = scaled
        return result
    finally:
        for obj in (img, transposed, converted, scaled, *intermediates):
            if obj is not None:
                with contextlib.suppress(Exception):
                    obj.close()
        # Принудительный GC после крупного PIL-объекта снижает RSS немедленно
        # вместо ожидания следующего поколения; критично при concurrency ≥ 2
        # и cgroup-лимите 2GB.
        gc.collect()
