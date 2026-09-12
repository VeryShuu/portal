"""Unit-тесты API модуля согласования (роутеры settings/documents, гейт
модуля, схемные валидации). Паттерн ``test_directum_api.py``: прямые вызовы
endpoint-функций с мок-БД (SimpleNamespace-строки) и monkeypatch клиентских
функций — без HTTP-приложения и реальных вызовов 1С.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import HTTPException
from prometheus_client import REGISTRY
from pydantic import ValidationError

from app.api.approvals.documents import (
    approve_document,
    bulk_approve,
    download_attachment,
    get_document,
    list_documents,
    reject_document,
)
from app.api.approvals.settings import check_connection, get_settings, put_settings
from app.api.deps import require_approvals_module
from app.core.modules_config import AllModuleSettings, ApprovalsModuleSettings
from app.schemas.approvals import (
    ApprovalDocument,
    ApprovalManagerOption,
    ApprovalsSettingsIn,
    ApproveIn,
    BulkApproveIn,
    RejectIn,
)
from app.services.approvals.client import ErpApprovalsError, ErpTransportError

BASE = "https://erp.test/MageErp/hs/Auth"


def _user() -> SimpleNamespace:
    return SimpleNamespace(id=uuid.uuid4(), email="u@mage.ru", role="user")


def _admin() -> SimpleNamespace:
    return SimpleNamespace(id=uuid.uuid4(), email="admin@mage.ru", role="admin")


def _row(**over) -> SimpleNamespace:
    values = dict(
        id=1,
        base_url=BASE,
        token_base_url=None,
        auth_username="Portal",
        auth_password_enc=None,
        updated_by_user_id=None,
        updated_at=datetime.now(UTC),
    )
    values.update(over)
    return SimpleNamespace(**values)


def _configured_row() -> SimpleNamespace:
    return _row(auth_password_enc="enc")


def _make_db(row: SimpleNamespace | None) -> MagicMock:
    db = MagicMock()
    # load_approvals_settings: (await db.scalars(select(...))).first() —
    # scalars() async, first() sync.
    scalars_result = MagicMock()
    scalars_result.first = MagicMock(return_value=row)
    db.scalars = AsyncMock(return_value=scalars_result)
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    return db


def _doc(guid="g-1", requires_manager=False, **over) -> ApprovalDocument:
    values = dict(
        guid=guid,
        doc_type="ЗаказПоставщику",
        number="УП-1",
        has_prices=True,
        requires_manager=requires_manager,
        managers=[ApprovalManagerOption(guid="m-1", name="Сидоров С.С.")]
        if requires_manager
        else [],
    )
    values.update(over)
    return ApprovalDocument(**values)


@pytest.fixture()
def _configured():
    """Все endpoints требуют настроенного подключения (503 иначе)."""
    with patch("app.api.approvals._common.decrypt_password", lambda row: "pw"):
        yield


@pytest.fixture(autouse=True)
def audit():
    """push_audit_event замокан на уровне documents-роутера: аудит пишет в
    Redis, в unit-тестах его не дёргаем, а assert'им вызовы (autouse — чтобы
    ни один тест не ушёл в реальный Redis; запрашивается по имени в тестах,
    которые проверяют вызовы)."""
    with patch("app.api.approvals.documents.push_audit_event", new=AsyncMock()) as audit:
        yield audit


class TestModuleGate:
    async def test_disabled_is_404(self):
        with (
            patch(
                "app.core.modules_config.load_modules_shared",
                AsyncMock(return_value=AllModuleSettings()),
            ),
            pytest.raises(HTTPException) as exc_info,
        ):
            await require_approvals_module(MagicMock())
        assert exc_info.value.status_code == 404

    async def test_enabled_passes(self):
        modules = AllModuleSettings(approvals=ApprovalsModuleSettings(enabled=True))
        with patch("app.core.modules_config.load_modules_shared", AsyncMock(return_value=modules)):
            assert await require_approvals_module(MagicMock()) is None


class TestSettingsApi:
    async def test_get_unconfigured(self):
        db = _make_db(_row())
        out = await get_settings(_admin(), db)
        assert out.configured is False
        assert out.password_set is False
        assert out.auth_username == "Portal"

    async def test_get_configured(self):
        db = _make_db(_configured_row())
        out = await get_settings(_admin(), db)
        assert out.configured is True
        assert out.password_set is True

    async def test_put_keeps_password_when_empty(self):
        db = _make_db(_configured_row())
        payload = ApprovalsSettingsIn(base_url=BASE, auth_username="Portal", auth_password=None)
        with (
            patch("app.api.approvals.settings.push_audit_event", new=AsyncMock()) as audit,
            patch("app.api.approvals.settings.encrypt_secret") as enc,
        ):
            out = await put_settings(payload, _admin(), db, MagicMock())
        enc.assert_not_called()
        assert out.password_set is True  # прежний шифр остался
        audit.assert_awaited_once()

    async def test_put_saves_new_password(self):
        db = _make_db(_row(auth_password_enc="old"))
        payload = ApprovalsSettingsIn(base_url=BASE, auth_username="Portal", auth_password="new")
        with (
            patch("app.api.approvals.settings.push_audit_event", new=AsyncMock()),
            patch("app.api.approvals.settings.encrypt_secret", return_value="enc-new"),
        ):
            out = await put_settings(payload, _admin(), db, MagicMock())
        assert out.base_url == BASE
        assert db.commit.await_count == 1

    async def test_test_endpoint_unconfigured_400(self):
        db = _make_db(_row())
        with pytest.raises(HTTPException) as exc_info:
            await check_connection(_admin(), db)
        assert exc_info.value.status_code == 400

    async def test_test_endpoint_ok(self):
        db = _make_db(_configured_row())
        with (
            patch("app.api.approvals.settings.decrypt_password", lambda row: "pw"),
            patch(
                "app.api.approvals.settings.client.ping",
                AsyncMock(return_value=(True, "ERP доступна", 42)),
            ) as ping,
        ):
            result = await check_connection(_admin(), db)
        assert result.ok is True
        assert result.latency_ms == 42
        ping.assert_awaited_once()

    async def test_test_endpoint_broken_password_400(self):
        db = _make_db(_configured_row())
        with (
            patch("app.api.approvals.settings.decrypt_password", lambda row: None),
            pytest.raises(HTTPException) as exc_info,
        ):
            await check_connection(_admin(), db)
        assert exc_info.value.status_code == 400


def _metric(action: str, outcome: str) -> float:
    """Текущее значение portal_approvals_actions_total (0, если серии ещё нет)."""
    value = REGISTRY.get_sample_value(
        "portal_approvals_actions_total", {"action": action, "outcome": outcome}
    )
    return value or 0.0


class TestDocumentsApi:
    async def test_list_ok(self, _configured):
        db = _make_db(_configured_row())
        with patch(
            "app.services.approvals.client.get_documents",
            AsyncMock(return_value=[_doc("g-1"), _doc("g-2")]),
        ):
            out = await list_documents(db, None, _user())
        assert out.total == 2
        assert [d.guid for d in out.items] == ["g-1", "g-2"]

    async def test_list_unconfigured_503(self):
        db = _make_db(_row(auth_password_enc=None))
        with pytest.raises(HTTPException) as exc_info:
            await list_documents(db, None, _user())
        assert exc_info.value.status_code == 503

    async def test_list_erp_forbidden_maps_403(self, _configured):
        db = _make_db(_configured_row())
        err = ErpApprovalsError("не ваш документ", status_code=403)
        with (
            patch("app.services.approvals.client.get_documents", AsyncMock(side_effect=err)),
            pytest.raises(HTTPException) as exc_info,
        ):
            await list_documents(db, None, _user())
        assert exc_info.value.status_code == 403

    async def test_list_bad_request_maps_400(self, _configured):
        db = _make_db(_configured_row())
        err = ErpApprovalsError("Employee не в группе", status_code=400)
        with (
            patch("app.services.approvals.client.get_documents", AsyncMock(side_effect=err)),
            pytest.raises(HTTPException) as exc_info,
        ):
            await list_documents(db, None, _user())
        assert exc_info.value.status_code == 400

    async def test_list_transport_maps_502(self, _configured):
        db = _make_db(_configured_row())
        err = ErpTransportError("ERP недоступна")
        with (
            patch("app.services.approvals.client.get_documents", AsyncMock(side_effect=err)),
            pytest.raises(HTTPException) as exc_info,
        ):
            await list_documents(db, None, _user())
        assert exc_info.value.status_code == 502

    async def test_get_document_with_attachments(self, _configured):
        db = _make_db(_configured_row())
        entry = {"ДвоичныеДанные": "#base64:QUFB", "ИмяФайла": "Счёт", "Расширение": "pdf"}
        with (
            patch(
                "app.services.approvals.client.get_documents",
                AsyncMock(return_value=[_doc("g-1")]),
            ),
            patch(
                "app.services.approvals.client.get_attachments",
                AsyncMock(return_value=[entry]),
            ),
        ):
            detail = await get_document("g-1", db, None, _user())
        assert detail.guid == "g-1"
        assert detail.attachments[0].name == "Счёт.pdf"

    async def test_get_unknown_document_404(self, _configured):
        db = _make_db(_configured_row())
        with (
            patch(
                "app.services.approvals.client.get_documents", AsyncMock(return_value=[_doc("g-1")])
            ),
            pytest.raises(HTTPException) as exc_info,
        ):
            await get_document("other", db, None, _user())
        assert exc_info.value.status_code == 404

    async def test_download_attachment(self, _configured):
        db = _make_db(_configured_row())
        with patch(
            "app.services.approvals.client.get_attachment_file",
            AsyncMock(return_value=("Счёт.pdf", b"PDF")),
        ):
            response = await download_attachment("g-1", 0, db, None, _user())
        assert response.body == b"PDF"
        assert "filename*" in response.headers["content-disposition"]

    async def test_approve_ok(self, _configured):
        db = _make_db(_configured_row())
        with (
            patch(
                "app.services.approvals.client.get_documents",
                AsyncMock(return_value=[_doc("g-1")]),
            ),
            patch(
                "app.services.approvals.client.approve",
                AsyncMock(return_value="Согласовано"),
            ) as approve,
        ):
            out = await approve_document("g-1", ApproveIn(comment="ок"), db, None, _user())
        assert out.ok is True
        assert out.message == "Согласовано"
        approve.assert_awaited_once()

    async def test_approve_requires_manager(self, _configured):
        db = _make_db(_configured_row())
        docs = [_doc("g-2", requires_manager=True)]
        with patch("app.services.approvals.client.get_documents", AsyncMock(return_value=docs)):
            # Без ответственного — 422.
            with pytest.raises(HTTPException) as exc_info:
                await approve_document("g-2", ApproveIn(), db, None, _user())
            assert exc_info.value.status_code == 422
            # Чужой GUID ответственного — 422.
            with pytest.raises(HTTPException):
                await approve_document("g-2", ApproveIn(manager_guid="nope"), db, None, _user())
            # Валидный — уходит в 1С с Employee.
            with patch(
                "app.services.approvals.client.approve", AsyncMock(return_value="ok")
            ) as approve:
                out = await approve_document(
                    "g-2", ApproveIn(manager_guid="m-1"), db, None, _user()
                )
        assert out.ok is True
        assert approve.await_args.kwargs["employee_guid"] == "m-1"

    async def test_approve_internal_order_generic_flow(self, _configured):
        # v2.1.0.0: 409-гейт снят — внутренние заказы согласуются в общем
        # потоке; generic-правило requires_manager продолжает действовать
        # (1С флагом «ТребуетсяОтветственный» требует Employee из
        # Пользователи[]).
        db = _make_db(_configured_row())
        docs = [
            _doc("g-int", doc_type="ЗаказНаВнутреннееПотребление", has_prices=False),
            _doc(
                "g-int-mgr",
                doc_type="ЗаказНаВнутреннееПотребление",
                has_prices=False,
                requires_manager=True,
            ),
        ]
        with patch("app.services.approvals.client.get_documents", AsyncMock(return_value=docs)):
            # requires_manager без ответственного — 422 (как у поставщика).
            with pytest.raises(HTTPException) as exc_info:
                await approve_document("g-int-mgr", ApproveIn(), db, None, _user())
            assert exc_info.value.status_code == 422
            # Без требования ответственного — согласуется как обычный документ.
            with patch(
                "app.services.approvals.client.approve", AsyncMock(return_value="Проведено")
            ) as approve:
                out = await approve_document("g-int", ApproveIn(comment="ок"), db, None, _user())
        assert out.ok is True
        approve.assert_awaited_once()

    async def test_reject_ok(self, _configured):
        db = _make_db(_configured_row())
        with (
            patch(
                "app.services.approvals.client.get_documents",
                AsyncMock(return_value=[_doc("g-1")]),
            ),
            patch(
                "app.services.approvals.client.reject", AsyncMock(return_value="Отклонено")
            ) as reject,
        ):
            out = await reject_document("g-1", RejectIn(comment="брак"), db, None, _user())
        assert out.ok is True
        reject.assert_awaited_once()

    async def test_bulk_mixed_results(self, _configured, monkeypatch):
        monkeypatch.setattr("app.services.approvals.client.BULK_APPROVE_PAUSE_SECONDS", 0)
        db = _make_db(_configured_row())
        docs = [
            _doc("g-1"),
            _doc("g-2", requires_manager=True),
            _doc("g-3", doc_type="ЗаказНаВнутреннееПотребление", has_prices=False),
        ]
        with (
            patch("app.services.approvals.client.get_documents", AsyncMock(return_value=docs)),
            patch("app.services.approvals.client.approve", AsyncMock(return_value="ok")),
        ):
            out = await bulk_approve(
                BulkApproveIn(uuids=["g-1", "g-2", "g-3", "alien"]), db, None, _user()
            )
        assert out.approved == 1
        assert out.failed == 3
        by_uuid = {r.uuid: r for r in out.results}
        assert by_uuid["g-1"].ok is True
        assert "ответственного" in by_uuid["g-2"].message
        # Внутренние из bulk исключены (свой выбор ответственного), но
        # согласуются по одному — сообщение это отражает.
        assert "по одному" in by_uuid["g-3"].message
        assert by_uuid["alien"].ok is False

    async def test_bulk_erp_error_maps_502(self, _configured):
        db = _make_db(_configured_row())
        err = ErpApprovalsError("сбой", status_code=500)
        with (
            patch("app.services.approvals.client.get_documents", AsyncMock(side_effect=err)),
            pytest.raises(HTTPException) as exc_info,
        ):
            await bulk_approve(BulkApproveIn(uuids=["g-1"]), db, None, _user())
        assert exc_info.value.status_code == 502

    async def test_bulk_transport_error_keeps_partial_report(self, _configured, monkeypatch):
        """Ревью 2026-09-05: обрыв связи на середине партии не должен ронять
        запрос в 500 (терялся отчёт по уже согласованным документам).
        Транспортная ошибка → хвост помечается «не обрабатывался», ERP больше
        не дёргается, частичный отчёт возвращается как обычно."""
        monkeypatch.setattr("app.services.approvals.client.BULK_APPROVE_PAUSE_SECONDS", 0)
        db = _make_db(_configured_row())
        docs = [_doc(f"g-{i}") for i in range(1, 4)]
        err = ErpTransportError("ERP недоступна: ReadTimeout")
        err.__cause__ = httpx.ReadTimeout("slow ERP")
        calls = {"n": 0}

        async def flaky(*_a, **_kw):
            calls["n"] += 1
            if calls["n"] == 1:
                return "ok"
            raise err

        with (
            patch("app.services.approvals.client.get_documents", AsyncMock(return_value=docs)),
            patch("app.services.approvals.client.approve", AsyncMock(side_effect=flaky)),
        ):
            out = await bulk_approve(BulkApproveIn(uuids=["g-1", "g-2", "g-3"]), db, None, _user())
        assert out.approved == 1
        assert out.failed == 2
        by_uuid = {r.uuid: r for r in out.results}
        assert by_uuid["g-1"].ok is True
        # Текущий документ: после таймаута проведение могло пройти — честно.
        assert "могло пройти" in by_uuid["g-2"].message
        # Хвост: не долбится в недоступную ERP.
        assert "не обрабатывался" in by_uuid["g-3"].message
        assert calls["n"] == 2


class TestObservability:
    """Статистика/аудит согласований: portal_approvals_actions_total +
    audit-события approvals.* (решение владельца 2026-09-07 — собирать
    статистику на портале, история по-прежнему в 1С)."""

    async def test_approve_pushes_audit_and_metric(self, _configured, audit):
        db = _make_db(_configured_row())
        before = _metric("approve", "ok")
        with (
            patch(
                "app.services.approvals.client.get_documents",
                AsyncMock(return_value=[_doc("g-1")]),
            ),
            patch(
                "app.services.approvals.client.approve",
                AsyncMock(return_value="Согласовано"),
            ),
        ):
            await approve_document("g-1", ApproveIn(comment="ок"), db, None, _user())
        assert _metric("approve", "ok") == before + 1
        audit.assert_awaited_once()
        kwargs = audit.await_args.kwargs
        assert kwargs["event_type"] == "approvals.approved"
        assert kwargs["resource_type"] == "approval_document"
        assert kwargs["resource_id"] == "g-1"
        assert kwargs["metadata"] == {"doc_type": "ЗаказПоставщику", "number": "УП-1"}

    async def test_approve_erp_error_counts_error_without_audit(self, _configured, audit):
        db = _make_db(_configured_row())
        before = _metric("approve", "error")
        err = ErpApprovalsError("ERP недоступна", status_code=502)
        with (
            patch(
                "app.services.approvals.client.get_documents",
                AsyncMock(return_value=[_doc("g-1")]),
            ),
            patch("app.services.approvals.client.approve", AsyncMock(side_effect=err)),
            pytest.raises(HTTPException) as exc_info,
        ):
            await approve_document("g-1", ApproveIn(), db, None, _user())
        assert exc_info.value.status_code == 502
        assert _metric("approve", "error") == before + 1
        # В аудит пишем только факты согласования, ошибки — в логи и метрику.
        audit.assert_not_called()

    async def test_reject_pushes_audit_and_metric(self, _configured, audit):
        db = _make_db(_configured_row())
        before = _metric("reject", "ok")
        with (
            patch(
                "app.services.approvals.client.get_documents",
                AsyncMock(return_value=[_doc("g-1")]),
            ),
            patch("app.services.approvals.client.reject", AsyncMock(return_value="Отклонено")),
        ):
            await reject_document("g-1", RejectIn(comment="брак"), db, None, _user())
        assert _metric("reject", "ok") == before + 1
        kwargs = audit.await_args.kwargs
        assert kwargs["event_type"] == "approvals.rejected"
        assert kwargs["resource_id"] == "g-1"

    async def test_reject_erp_error_counts_error_without_audit(self, _configured, audit):
        db = _make_db(_configured_row())
        before = _metric("reject", "error")
        err = ErpApprovalsError("сбой проведения", status_code=500)
        with (
            patch(
                "app.services.approvals.client.get_documents",
                AsyncMock(return_value=[_doc("g-1")]),
            ),
            patch("app.services.approvals.client.reject", AsyncMock(side_effect=err)),
            pytest.raises(HTTPException) as exc_info,
        ):
            await reject_document("g-1", RejectIn(comment="брак"), db, None, _user())
        assert exc_info.value.status_code == 502
        assert _metric("reject", "error") == before + 1
        audit.assert_not_called()

    async def test_bulk_all_ok_counts_ok(self, _configured, monkeypatch, audit):
        monkeypatch.setattr("app.services.approvals.client.BULK_APPROVE_PAUSE_SECONDS", 0)
        db = _make_db(_configured_row())
        docs = [_doc("g-1"), _doc("g-2")]
        before = _metric("bulk_approve", "ok")
        with (
            patch("app.services.approvals.client.get_documents", AsyncMock(return_value=docs)),
            patch("app.services.approvals.client.approve", AsyncMock(return_value="ok")),
        ):
            out = await bulk_approve(BulkApproveIn(uuids=["g-1", "g-2"]), db, None, _user())
        assert out.failed == 0
        assert _metric("bulk_approve", "ok") == before + 1

    async def test_bulk_partial_pushes_audit_and_metric(self, _configured, monkeypatch, audit):
        monkeypatch.setattr("app.services.approvals.client.BULK_APPROVE_PAUSE_SECONDS", 0)
        db = _make_db(_configured_row())
        docs = [_doc("g-1"), _doc("g-2", requires_manager=True)]
        before = _metric("bulk_approve", "partial")
        with (
            patch("app.services.approvals.client.get_documents", AsyncMock(return_value=docs)),
            patch("app.services.approvals.client.approve", AsyncMock(return_value="ok")),
        ):
            out = await bulk_approve(BulkApproveIn(uuids=["g-1", "g-2"]), db, None, _user())
        assert out.approved == 1
        assert out.failed == 1
        assert _metric("bulk_approve", "partial") == before + 1
        kwargs = audit.await_args.kwargs
        assert kwargs["event_type"] == "approvals.bulk_approved"
        assert kwargs["metadata"]["approved"] == 1
        assert kwargs["metadata"]["uuids"] == ["g-1", "g-2"]

    async def test_bulk_all_skipped_counts_error(self, _configured, monkeypatch, audit):
        monkeypatch.setattr("app.services.approvals.client.BULK_APPROVE_PAUSE_SECONDS", 0)
        db = _make_db(_configured_row())
        docs = [_doc("g-2", requires_manager=True)]
        before = _metric("bulk_approve", "error")
        with (
            patch("app.services.approvals.client.get_documents", AsyncMock(return_value=docs)),
            patch("app.services.approvals.client.approve", AsyncMock(return_value="ok")) as approve,
        ):
            out = await bulk_approve(BulkApproveIn(uuids=["g-2"]), db, None, _user())
        assert out.approved == 0
        assert _metric("bulk_approve", "error") == before + 1
        approve.assert_not_called()  # skip до вызова 1С, но попытка посчитана

    async def test_attachment_download_audited_only_in_logs(self, _configured, audit):
        """Вложения — в логи (approvals.attachment_downloaded), не в аудит:
        каждое открытие файла не должно шуметь в журнале аудита."""
        db = _make_db(_configured_row())
        with patch(
            "app.services.approvals.client.get_attachment_file",
            AsyncMock(return_value=("Счёт.pdf", b"PDF")),
        ):
            await download_attachment("g-1", 0, db, None, _user())
        audit.assert_not_called()


class TestRouting:
    """Регрессия: Depends(Annotated-алиас) в router-level dependencies
    (FastAPI 0.140) генерирует фантомные обязательные query-параметры
    args/kwargs — endpoint отвечает 422 на любой запрос. Гейт должен
    оборачиваться сырой функцией (как в directum)."""

    def test_settings_route_not_shadowed_by_document_uuid(self):
        # Регрессия: GET /approvals/settings должен резолвиться в
        # get_settings, а не в get_document («settings» матчится как
        # document_uuid при неверном порядке включения роутеров).
        from unittest.mock import AsyncMock, MagicMock

        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from app.api.approvals import router as approvals_router
        from app.api.deps import get_current_user, get_db, get_redis, require_approvals_module

        app = FastAPI()
        app.include_router(approvals_router, prefix="/api/v1")

        admin = SimpleNamespace(id=uuid.uuid4(), email="a@mage.ru", role="admin")
        scalars_result = MagicMock()
        scalars_result.first = MagicMock(
            return_value=SimpleNamespace(
                id=1,
                base_url="https://erp.test/x",
                token_base_url=None,
                auth_username="Portal",
                auth_password_enc="enc",
                updated_at=datetime.now(UTC),
            )
        )
        db = MagicMock()
        db.scalars = AsyncMock(return_value=scalars_result)

        app.dependency_overrides[get_current_user] = lambda: admin
        app.dependency_overrides[require_approvals_module] = lambda: None
        app.dependency_overrides[get_redis] = lambda: MagicMock()
        app.dependency_overrides[get_db] = lambda: db

        with patch("app.api.approvals._common.decrypt_password", lambda row: "pw"):
            client = TestClient(app)
            resp = client.get("/api/v1/approvals/settings")

        assert resp.status_code == 200, (
            f"GET /approvals/settings перекрыт /approvals/{{document_uuid}}: "
            f"{resp.status_code} {resp.text[:200]}"
        )
        assert resp.json()["auth_username"] == "Portal"

    def test_no_phantom_query_params_in_openapi(self):
        from fastapi import FastAPI
        from fastapi.openapi.utils import get_openapi

        from app.api.approvals import router as approvals_router

        app = FastAPI()
        app.include_router(approvals_router, prefix="/api/v1")
        spec = get_openapi(title="t", version="1", routes=app.routes)
        approvals_paths = {path: ops for path, ops in spec["paths"].items() if "/approvals" in path}
        assert approvals_paths, "approvals routes не зарегистрировались"
        for path, ops in approvals_paths.items():
            for method, op in ops.items():
                params = [p["name"] for p in op.get("parameters", [])]
                assert "args" not in params and "kwargs" not in params, (
                    f"фантомные query-параметры на {method.upper()} {path}: {params}"
                )


class TestSchemaValidation:
    def test_reject_blank_comment_rejected(self):
        with pytest.raises(ValidationError):
            RejectIn(comment="   ")

    def test_settings_bad_scheme_rejected(self):
        with pytest.raises(ValidationError):
            ApprovalsSettingsIn(base_url="erp.mage.ru/hs")

    def test_settings_strips_trailing_slash(self):
        payload = ApprovalsSettingsIn(base_url=f"{BASE}/", auth_username=" Portal ")
        assert payload.base_url == BASE
        assert payload.auth_username == "Portal"

    def test_bulk_empty_uuids_rejected(self):
        with pytest.raises(ValidationError):
            BulkApproveIn(uuids=["  "])

    def test_bulk_limit_20(self):
        """Ревью 2026-09-05: партия 50 не укладывалась в таймаут интерфейса
        (одни паузы — ~25с). Лимит 20 — зеркало BULK_APPROVE_MAX фронта."""
        assert BulkApproveIn(uuids=[str(uuid.uuid4()) for _ in range(20)]).uuids
        with pytest.raises(ValidationError):
            BulkApproveIn(uuids=[str(uuid.uuid4()) for _ in range(21)])
