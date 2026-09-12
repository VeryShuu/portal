"""Pydantic-схемы модуля «Согласование документов» (docs/wip/erp-approvals.md).

Два слоя:

* Settings (singleton ``approvals_settings``) — клон directum-схем: пароль
  write-only, в ответе только ``password_set: bool``.
* Документы 1С — нормализация кириллических ключей JSON в snake_case
  (фронтенд не должен знать про «НаименованиеДокумента»). Сырой ответ 1С
  парсит :mod:`app.services.approvals.client`, схемы — DTO для API.

Контракт ошибок 1С (пакет доработок 2026-09-04): честные HTTP-коды + JSON
``{"Result": "OK"|"Error", "Code": ..., "Message": "..."}``; клиент
дополнительно терпит легаси-ответы (200 + сырой текст).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

# Тип документа, у которого есть цены/суммы/контрагент/проект. Прочие типы
# (Заказ на внутреннее потребление и т.п.) — без цен (1С отдаёт нули намеренно,
# скрытие цен) и без «Согласовать» до назначения ответственного.
SUPPLIER_ORDER_TYPE = "ЗаказПоставщику"

# Легаси-правило «нужно выбрать ответственного»: сверка текста последнего
# этапа (старый PHP так и жил). Новый контракт — вычисляемое поле
# «ТребуетсяОтветственный» в DocumentsForApproval; строка ниже — fallback,
# если 1С-пакет ещё не внедрён. Вынесено в константу: при опечатке на стороне
# 1С правило тихо перестаёт срабатывать (см. «Грабли» в wip-плане).
LEGACY_MANAGER_STAGE = "Руководитель ЦЗ Заказа на внутреннее потребление"

# Максимум документов в одной партии массового согласования. Партия идёт
# строго последовательно с паузами (каждый GETAgreed проводит документ в 1С):
# при лимите 50 даже одни паузы занимали ~25с и запрос не укладывался в
# таймаут интерфейса 30с (ревью 2026-09-05). Зеркало на фронте —
# BULK_APPROVE_MAX в frontend/src/api/approvals.ts.
BULK_APPROVE_MAX = 20


# ── Settings (singleton) ────────────────────────────────────────────────────


class ApprovalsSettingsIn(BaseModel):
    """Настройки подключения к ERP. ``auth_password`` — write-only: пусто/None
    = оставить сохранённый шифр (паттерн matrix-бота/directum)."""

    base_url: str = Field(default="https://erp.mage.ru/MageErp/hs/Auth", max_length=255)
    # Выдача токенов (GETTokenByLogin) может жить на отдельном RootURL
    # (миграция 116: 1С публикует …/hs/PortalAuth). Пусто = как base_url.
    token_base_url: str = Field(default="", max_length=255)
    auth_username: str = Field(default="Portal", min_length=1, max_length=255)
    auth_password: str | None = Field(default=None, min_length=1, max_length=512)

    @field_validator("base_url", "token_base_url")
    @classmethod
    def validate_base_url_scheme(cls, v: str) -> str:
        # scheme обязателен: httpx без него падает на ровном месте (как
        # portal_base_url / directum base_url).
        v = v.strip()
        if not v:
            return v
        if not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError("must start with http:// or https://")
        return v.rstrip("/")

    @field_validator("auth_username")
    @classmethod
    def strip_username(cls, v: str) -> str:
        # Логин копипастой — хвостовой пробел ломает basic auth.
        v = v.strip()
        if not v:
            raise ValueError("auth_username must not be empty")
        return v

    @field_validator("auth_password")
    @classmethod
    def strip_password(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        return v or None


class ApprovalsSettingsOut(BaseModel):
    base_url: str
    token_base_url: str  # пусто = совпадает с base_url
    auth_username: str
    password_set: bool
    configured: bool
    updated_at: datetime


class ApprovalsTestResult(BaseModel):
    """Результат POST /approvals/test — проверка доступности ERP и Basic-кредов.

    Проверка выполняется запросом ``DocumentsForApproval`` с заведомо
    фиктивным профилем: транспортный успех + структура ответа 1С означают
    «сервис доступен, учётка принята» (валидность самого токена не проверяется).
    """

    ok: bool
    message: str
    latency_ms: int


# ── Документы (нормализация ответа DocumentsForApproval) ───────────────────


class ApprovalHistoryItem(BaseModel):
    """Этап согласования: ``ИсторияСогласования[]`` из 1С."""

    period: str = ""
    user: str = ""
    event: str = ""
    comment: str = ""
    stage: str = ""


class ApprovalProduct(BaseModel):
    """Строка «Товары». ``price``/``total`` = None для документов без цен
    (1С отдаёт нули намеренно — скрытие цен; None ≠ 0 в UI). ``recipient`` —
    «Получатель» (подразделение-получатель; у внутренних заказов это шапочное
    подразделение, одинаковое во всех строках — v2.1.0.0)."""

    name: str = ""
    recipient: str = ""
    quantity: str = ""
    price: float | None = None
    total: float | None = None  # «СуммаСНДС» = сумма строки с НДС


class ApprovalManagerOption(BaseModel):
    """Кандидат в «ответственного» (``Пользователи[]``): GUID уходит в
    GETAgreed параметром Employee."""

    guid: str
    name: str


class ApprovalDocument(BaseModel):
    """Документ на согласование (нормализованный)."""

    guid: str
    doc_type: str  # «НаименованиеДокумента» (SUPPLIER_ORDER_TYPE | …)
    number: str = ""
    date: str = ""  # отображаемая дата как в 1С (формат не гарантирован)
    organization: str = ""
    manager: str = ""  # «Менеджер» / «Ответственный»
    comment: str = ""
    contractor: str | None = None  # только ЗаказПоставщику
    project: str | None = None  # только ЗаказПоставщику
    amount: float | None = None  # «СуммаДокумента»
    currency: str | None = None
    activity_direction: str | None = None  # только внутренние заказы
    # Гиперссылка на задачу СЭД («СсылкаНаЗадачуСЭД» из 1С, есть не у всех
    # документов: пустая строка/отсутствие поля → None — строка в UI скрыта).
    sed_url: str | None = None
    # Признак «перед согласованием выбрать ответственного» (и отказаться от
    # массового согласования). Новое поле «ТребуетсяОтветственный» из 1С;
    # fallback — легаси-сверка текста этапа.
    requires_manager: bool = False
    has_prices: bool = False
    history: list[ApprovalHistoryItem] = Field(default_factory=list)
    products: list[ApprovalProduct] = Field(default_factory=list)
    managers: list[ApprovalManagerOption] = Field(default_factory=list)


class ApprovalAttachmentInfo(BaseModel):
    """Метаданные вложения (без байтов): скачивание — отдельным GET по index."""

    index: int
    name: str  # «ИмяФайла.Расширение»


class ApprovalDocumentDetail(ApprovalDocument):
    attachments: list[ApprovalAttachmentInfo] = Field(default_factory=list)


class ApprovalDocumentList(BaseModel):
    """Список на согласование. Пагинация не проталкивается в 1С (сервис
    отдаёт весь список) — {items, total} без limit/offset (осознанное
    отклонение от конвенции, см. модульный док)."""

    items: list[ApprovalDocument]
    total: int


# ── Действия ────────────────────────────────────────────────────────────────


class ApproveIn(BaseModel):
    """Согласование. ``manager_guid`` обязателен, когда документ
    ``requires_manager`` (проверка в роутере — там контекст документа)."""

    comment: str = Field(default="", max_length=2000)
    manager_guid: str | None = Field(default=None, max_length=64)


class RejectIn(BaseModel):
    """Отклонение — комментарий обязателен (как в старом UI: кнопка
    разблокируется только при непустом комментарии)."""

    comment: str = Field(min_length=1, max_length=2000)

    @field_validator("comment")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("comment must not be blank")
        return v.strip()


class ActionOut(BaseModel):
    ok: bool
    message: str = ""  # текст-подтверждение 1С (показывался и в старом UI)


class BulkApproveIn(BaseModel):
    uuids: list[str] = Field(min_length=1, max_length=BULK_APPROVE_MAX)

    @field_validator("uuids")
    @classmethod
    def clean_uuids(cls, v: list[str]) -> list[str]:
        cleaned = [u.strip() for u in v if u and u.strip()]
        if not cleaned:
            raise ValueError("uuids must not be empty")
        return cleaned


class BulkApproveItemResult(BaseModel):
    uuid: str
    ok: bool
    message: str = ""


class BulkApproveOut(BaseModel):
    """Массовое согласование: по-документные результаты (part success —
    часть документов может уйти, часть отказать; 1С-вызов последовательный
    с паузой, параллелить нельзя — каждый GETAgreed проводит документ)."""

    results: list[BulkApproveItemResult]
    approved: int
    failed: int
