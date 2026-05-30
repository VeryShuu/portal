from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

NOW = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
NEWS_ID = uuid.uuid4()
POLL_ID = uuid.uuid4()


def _make_db() -> AsyncMock:
    db = AsyncMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.add = MagicMock()
    db.delete = AsyncMock()
    return db


def _make_option(
    oid: uuid.UUID | None = None, text: str = "Option A", sort_order: int = 0
) -> SimpleNamespace:
    o = SimpleNamespace()
    o.id = oid or uuid.uuid4()
    o.text = text
    o.image_url = None
    o.sort_order = sort_order
    o.votes_count = 0
    return o


def _make_question(
    qid: uuid.UUID | None = None,
    text: str = "Question?",
    sort_order: int = 0,
    is_required: bool = True,
    is_multiple: bool = False,
    max_choices: int | None = None,
    allow_custom_answer: bool = False,
    options: list | None = None,
) -> SimpleNamespace:
    q = SimpleNamespace()
    q.id = qid or uuid.uuid4()
    q.text = text
    q.sort_order = sort_order
    q.is_required = is_required
    q.is_multiple = is_multiple
    q.max_choices = max_choices
    q.allow_custom_answer = allow_custom_answer
    q.options = options or [_make_option(), _make_option(text="Option B")]
    return q


def _make_poll(
    poll_id: uuid.UUID | None = None,
    questions: list | None = None,
    allow_revote: bool = False,
    is_anonymous: bool = True,
    results_visibility: str = "after_vote",
    closed_at: datetime | None = None,
    closes_at: datetime | None = None,
    updated_at: datetime | None = None,
) -> SimpleNamespace:
    p = SimpleNamespace()
    p.id = poll_id or uuid.uuid4()
    p.news_id = NEWS_ID
    p.questions = questions or []
    p.allow_revote = allow_revote
    p.is_anonymous = is_anonymous
    p.results_visibility = results_visibility
    p.closed_at = closed_at
    p.closes_at = closes_at
    p.updated_at = updated_at or NOW
    return p


def _make_create_option(text: str = "Opt", image_url: str | None = None, sort_order: int = 0):
    from app.schemas.news_poll import CreateNewsPollOption

    return CreateNewsPollOption(text=text, image_url=image_url, sort_order=sort_order)


def _make_create_question(
    text: str = "Q?",
    options: list | None = None,
    sort_order: int = 0,
    is_required: bool = True,
    is_multiple: bool = False,
    max_choices: int | None = None,
    allow_custom_answer: bool = False,
):
    from app.schemas.news_poll import CreateNewsPollQuestion

    return CreateNewsPollQuestion(
        text=text,
        sort_order=sort_order,
        is_required=is_required,
        is_multiple=is_multiple,
        max_choices=max_choices,
        allow_custom_answer=allow_custom_answer,
        options=options or [_make_create_option("A"), _make_create_option("B")],
    )


def _make_update_option(**kwargs):
    from app.schemas.news_poll import UpdateNewsPollOption

    return UpdateNewsPollOption(**kwargs)


def _make_update_question(**kwargs):
    from app.schemas.news_poll import UpdateNewsPollQuestion

    return UpdateNewsPollQuestion(**kwargs)


def _make_update_request(**kwargs):
    from app.schemas.news_poll import UpdateNewsPollRequest

    return UpdateNewsPollRequest(**kwargs)


class TestBuildQuestion:
    def test_builds_with_defaults(self):
        from app.services.news.poll.crud import _build_question

        q_schema = _make_create_question()
        result = _build_question(q_schema, default_sort=0)
        assert result.text == "Q?"
        assert len(result.options) == 2

    def test_uses_default_sort_when_zero(self):
        from app.services.news.poll.crud import _build_question

        q_schema = _make_create_question(sort_order=0)
        result = _build_question(q_schema, default_sort=5)
        assert result.sort_order == 5

    def test_uses_explicit_sort(self):
        from app.services.news.poll.crud import _build_question

        q_schema = _make_create_question(sort_order=3)
        result = _build_question(q_schema, default_sort=0)
        assert result.sort_order == 3

    def test_options_with_default_sort(self):
        from app.schemas.news_poll import CreateNewsPollOption
        from app.services.news.poll.crud import _build_question

        opts = [
            CreateNewsPollOption(text="A", sort_order=0),
            CreateNewsPollOption(text="B", sort_order=0),
        ]
        q_schema = _make_create_question(options=opts)
        result = _build_question(q_schema, default_sort=0)
        assert result.options[0].sort_order == 0
        assert result.options[1].sort_order == 1


class TestCreatePoll:
    @pytest.mark.asyncio
    async def test_news_not_found_raises_404(self):
        from app.services.news.poll.crud import create_poll

        db = _make_db()
        result_news = MagicMock()
        result_news.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=result_news)

        data = MagicMock()
        data.questions = []
        with pytest.raises(HTTPException) as exc_info:
            await create_poll(db, NEWS_ID, data)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_poll_already_exists_raises_400(self):
        from app.services.news.poll.crud import create_poll

        db = _make_db()
        news_mock = MagicMock()

        result_news = MagicMock()
        result_news.scalar_one_or_none.return_value = news_mock

        result_existing = MagicMock()
        result_existing.scalar_one_or_none.return_value = uuid.uuid4()

        db.execute = AsyncMock(side_effect=[result_news, result_existing])

        data = MagicMock()
        data.questions = []
        with pytest.raises(HTTPException) as exc_info:
            await create_poll(db, NEWS_ID, data)
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_creates_poll_successfully(self):
        from app.schemas.news_poll import CreateNewsPollRequest
        from app.services.news.poll.crud import create_poll

        db = _make_db()
        news_mock = MagicMock()

        result_news = MagicMock()
        result_news.scalar_one_or_none.return_value = news_mock

        result_existing = MagicMock()
        result_existing.scalar_one_or_none.return_value = None

        db.execute = AsyncMock(side_effect=[result_news, result_existing])
        db.refresh = AsyncMock(side_effect=lambda obj: None)

        data = CreateNewsPollRequest(
            questions=[_make_create_question()],
        )

        await create_poll(db, NEWS_ID, data)

        db.commit.assert_awaited()
        db.refresh.assert_awaited()


class TestApplyPollSettings:
    def test_restricted_frozen_field_changed_raises_403(self):
        from app.services.news.poll.crud import _apply_poll_settings

        poll = _make_poll(is_anonymous=True)
        data = _make_update_request(is_anonymous=False)
        with pytest.raises(HTTPException) as exc_info:
            _apply_poll_settings(poll, data, restricted=True)
        assert exc_info.value.status_code == 403

    def test_restricted_frozen_field_same_value_ok(self):
        from app.services.news.poll.crud import _apply_poll_settings

        poll = _make_poll(is_anonymous=True)
        data = _make_update_request(is_anonymous=True)
        _apply_poll_settings(poll, data, restricted=True)

    def test_restricted_editable_field_updated(self):
        from app.services.news.poll.crud import _apply_poll_settings

        new_closes_at = datetime(2025, 1, 1, tzinfo=UTC)
        poll = _make_poll()
        poll.closes_at = None
        data = _make_update_request(closes_at=new_closes_at)
        _apply_poll_settings(poll, data, restricted=True)
        assert poll.closes_at == new_closes_at

    def test_unrestricted_all_fields_updated(self):
        from app.services.news.poll.crud import _apply_poll_settings

        poll = _make_poll(is_anonymous=True, allow_revote=False)
        data = _make_update_request(is_anonymous=False, allow_revote=True)
        _apply_poll_settings(poll, data, restricted=False)
        assert poll.is_anonymous is False
        assert poll.allow_revote is True


class TestApplyQuestionSettings:
    def test_restricted_frozen_field_changed_raises_403(self):
        from app.services.news.poll.crud import _apply_question_settings

        q = _make_question(is_required=True)
        inp = _make_update_question(id=q.id, is_required=False)
        with pytest.raises(HTTPException) as exc_info:
            _apply_question_settings(q, inp, restricted=True)
        assert exc_info.value.status_code == 403

    def test_restricted_editable_text_updated(self):
        from app.services.news.poll.crud import _apply_question_settings

        q = _make_question(text="old")
        inp = _make_update_question(id=q.id, text="new")
        _apply_question_settings(q, inp, restricted=True)
        assert q.text == "new"

    def test_unrestricted_all_fields_updated(self):
        from app.services.news.poll.crud import _apply_question_settings

        q = _make_question(is_required=True, is_multiple=False)
        inp = _make_update_question(id=q.id, is_required=False, is_multiple=True)
        _apply_question_settings(q, inp, restricted=False)
        assert q.is_required is False
        assert q.is_multiple is True

    def test_unrestricted_max_choices_without_multiple_raises(self):
        from app.services.news.poll.crud import _apply_question_settings

        q = _make_question(is_multiple=False)
        q.max_choices = 2
        inp = _make_update_question(id=q.id, max_choices=2)
        with pytest.raises(HTTPException) as exc_info:
            _apply_question_settings(q, inp, restricted=False)
        assert exc_info.value.status_code == 400

    def test_unrestricted_max_choices_less_than_1_raises(self):
        from app.services.news.poll.crud import _apply_question_settings

        q = _make_question(is_multiple=True)
        q.max_choices = 0
        inp = _make_update_question(id=q.id, is_multiple=True, max_choices=0)
        with pytest.raises(HTTPException) as exc_info:
            _apply_question_settings(q, inp, restricted=False)
        assert exc_info.value.status_code == 400


class TestApplyOptionsLocked:
    def test_none_options_returns_early(self):
        from app.services.news.poll.crud import _apply_options_locked

        q = _make_question()
        _apply_options_locked(q, None)

    def test_different_count_raises_403(self):
        from app.services.news.poll.crud import _apply_options_locked

        opt = _make_option()
        q = _make_question(options=[opt, _make_option()])
        inp_options = [_make_update_option(id=opt.id, text="new")]
        with pytest.raises(HTTPException) as exc_info:
            _apply_options_locked(q, inp_options)
        assert exc_info.value.status_code == 403

    def test_missing_option_id_raises_403(self):
        from app.services.news.poll.crud import _apply_options_locked

        opt1 = _make_option()
        opt2 = _make_option()
        q = _make_question(options=[opt1, opt2])
        inp_options = [
            _make_update_option(id=opt1.id, text="new"),
            _make_update_option(id=uuid.uuid4(), text="other"),
        ]
        with pytest.raises(HTTPException) as exc_info:
            _apply_options_locked(q, inp_options)
        assert exc_info.value.status_code == 403

    def test_sort_order_change_raises_403(self):
        from app.services.news.poll.crud import _apply_options_locked

        opt1 = _make_option(sort_order=0)
        opt2 = _make_option(sort_order=1)
        q = _make_question(options=[opt1, opt2])
        inp_options = [
            _make_update_option(id=opt1.id, text="A", sort_order=5),
            _make_update_option(id=opt2.id, text="B", sort_order=1),
        ]
        with pytest.raises(HTTPException) as exc_info:
            _apply_options_locked(q, inp_options)
        assert exc_info.value.status_code == 403

    def test_text_update_allowed(self):
        from app.services.news.poll.crud import _apply_options_locked

        opt1 = _make_option(sort_order=0)
        opt2 = _make_option(sort_order=1)
        q = _make_question(options=[opt1, opt2])
        inp_options = [
            _make_update_option(id=opt1.id, text="updated A"),
            _make_update_option(id=opt2.id, text="updated B"),
        ]
        _apply_options_locked(q, inp_options)
        assert opt1.text == "updated A"

    def test_image_change_raises_403(self):
        from app.services.news.poll.crud import _apply_options_locked

        opt1 = _make_option(sort_order=0)
        opt1.image_url = "http://old.png"
        opt2 = _make_option(sort_order=1)
        q = _make_question(options=[opt1, opt2])
        inp_options = [
            _make_update_option(id=opt1.id, image_url="http://new.png"),
            _make_update_option(id=opt2.id),
        ]
        with pytest.raises(HTTPException) as exc_info:
            _apply_options_locked(q, inp_options)
        assert exc_info.value.status_code == 403


class TestApplyOptionsUnlocked:
    @pytest.mark.asyncio
    async def test_none_options_returns_early(self):
        from app.services.news.poll.crud import _apply_options_unlocked

        db = _make_db()
        q = _make_question()
        await _apply_options_unlocked(db, q, None)

    @pytest.mark.asyncio
    async def test_too_few_options_raises(self):
        from app.services.news.poll.crud import _apply_options_unlocked

        db = _make_db()
        q = _make_question()
        inp = [_make_update_option(text="A")]
        with pytest.raises(HTTPException) as exc_info:
            await _apply_options_unlocked(db, q, inp)
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_duplicate_option_texts_raises(self):
        from app.services.news.poll.crud import _apply_options_unlocked

        db = _make_db()
        q = _make_question()
        inp = [_make_update_option(text="Same"), _make_update_option(text="same")]
        with pytest.raises(HTTPException) as exc_info:
            await _apply_options_unlocked(db, q, inp)
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_removes_options_not_in_input(self):
        from app.services.news.poll.crud import _apply_options_unlocked

        db = _make_db()
        opt1 = _make_option()
        opt2 = _make_option()
        q = _make_question(options=[opt1, opt2])
        inp = [_make_update_option(id=opt1.id, text="A"), _make_update_option(text="B")]
        await _apply_options_unlocked(db, q, inp)
        db.delete.assert_awaited_once_with(opt2)

    @pytest.mark.asyncio
    async def test_updates_existing_option(self):
        from app.services.news.poll.crud import _apply_options_unlocked

        db = _make_db()
        opt1 = _make_option()
        q = _make_question(options=[opt1])

        from app.schemas.news_poll import UpdateNewsPollOption

        inp_opt = UpdateNewsPollOption(id=opt1.id, text="Updated")
        inp = [inp_opt, _make_update_option(text="New Option")]
        await _apply_options_unlocked(db, q, inp)
        assert opt1.text == "Updated"

    @pytest.mark.asyncio
    async def test_adds_new_option(self):
        from app.services.news.poll.crud import _apply_options_unlocked

        db = _make_db()
        opt1 = _make_option()
        q = _make_question(options=[opt1])
        q.options = [opt1]

        inp = [
            _make_update_option(id=opt1.id, text="A"),
            _make_update_option(text="B"),
        ]
        initial_len = len(q.options)
        await _apply_options_unlocked(db, q, inp)
        assert len(q.options) > initial_len

    @pytest.mark.asyncio
    async def test_new_option_without_text_or_image_raises(self):
        from app.schemas.news_poll import UpdateNewsPollOption
        from app.services.news.poll.crud import _apply_options_unlocked

        db = _make_db()
        opt1 = _make_option()
        q = _make_question(options=[opt1])

        inp = [
            _make_update_option(id=opt1.id, text="A"),
            UpdateNewsPollOption(id=None, text=None, image_url=None, sort_order=1),
        ]
        with pytest.raises(HTTPException) as exc_info:
            await _apply_options_unlocked(db, q, inp)
        assert exc_info.value.status_code == 400


class TestApplyQuestions:
    @pytest.mark.asyncio
    async def test_none_questions_returns_early(self):
        from app.services.news.poll.crud import _apply_questions

        db = _make_db()
        poll = _make_poll()
        await _apply_questions(db, poll, None, restricted=False)

    @pytest.mark.asyncio
    async def test_empty_questions_unrestricted_raises(self):
        from app.services.news.poll.crud import _apply_questions

        db = _make_db()
        poll = _make_poll(questions=[_make_question()])
        with pytest.raises(HTTPException) as exc_info:
            await _apply_questions(db, poll, [], restricted=False)
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_too_many_questions_raises(self):
        from app.services.news.poll.crud import _apply_questions

        db = _make_db()
        poll = _make_poll()
        inp = [_make_update_question() for _ in range(31)]
        with pytest.raises(HTTPException) as exc_info:
            await _apply_questions(db, poll, inp, restricted=False)
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_restricted_add_remove_questions_raises(self):
        from app.services.news.poll.crud import _apply_questions

        db = _make_db()
        q = _make_question()
        poll = _make_poll(questions=[q])
        inp = [_make_update_question()]
        with pytest.raises(HTTPException) as exc_info:
            await _apply_questions(db, poll, inp, restricted=True)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_restricted_updates_existing_question(self):
        from app.services.news.poll.crud import _apply_questions

        db = _make_db()
        q = _make_question(text="old")
        poll = _make_poll(questions=[q])
        inp = [_make_update_question(id=q.id, text="new")]
        await _apply_questions(db, poll, inp, restricted=True)
        assert q.text == "new"

    @pytest.mark.asyncio
    async def test_unrestricted_deletes_removed_question(self):
        from app.services.news.poll.crud import _apply_questions

        db = _make_db()
        q1 = _make_question()
        q2 = _make_question()
        poll = _make_poll(questions=[q1, q2])
        inp = [_make_update_question(id=q1.id, text="updated")]
        await _apply_questions(db, poll, inp, restricted=False)
        db.delete.assert_awaited_once_with(q2)

    @pytest.mark.asyncio
    async def test_unrestricted_new_question_no_text_raises(self):
        from app.services.news.poll.crud import _apply_questions

        db = _make_db()
        poll = _make_poll()
        inp = [_make_update_question()]
        with pytest.raises(HTTPException) as exc_info:
            await _apply_questions(db, poll, inp, restricted=False)
        assert exc_info.value.status_code == 400


class TestUpdatePoll:
    @pytest.mark.asyncio
    async def test_poll_not_found_raises_404(self):
        from app.services.news.poll.crud import update_poll

        db = _make_db()
        data = _make_update_request()
        with patch(
            "app.services.news.poll.crud.get_poll_by_news_id", new=AsyncMock(return_value=None)
        ):
            with pytest.raises(HTTPException) as exc_info:
                await update_poll(db, NEWS_ID, data)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_update_poll_no_votes(self):
        from app.services.news.poll.crud import update_poll

        poll = _make_poll()
        db = _make_db()

        result_count = MagicMock()
        result_count.scalar_one.return_value = 0
        db.execute = AsyncMock(return_value=result_count)

        data = _make_update_request(closes_at=datetime(2025, 1, 1, tzinfo=UTC))

        with patch(
            "app.services.news.poll.crud.get_poll_by_news_id", new=AsyncMock(return_value=poll)
        ):
            await update_poll(db, NEWS_ID, data)

        db.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_update_poll_with_votes_restricted(self):
        from app.services.news.poll.crud import update_poll

        poll = _make_poll(is_anonymous=True)
        db = _make_db()

        result_count = MagicMock()
        result_count.scalar_one.return_value = 5
        db.execute = AsyncMock(return_value=result_count)

        data = _make_update_request(is_anonymous=True)

        with patch(
            "app.services.news.poll.crud.get_poll_by_news_id", new=AsyncMock(return_value=poll)
        ):
            await update_poll(db, NEWS_ID, data)

        db.commit.assert_awaited()


class TestDeletePoll:
    @pytest.mark.asyncio
    async def test_poll_not_found_raises_404(self):
        from app.services.news.poll.crud import delete_poll

        db = _make_db()
        with patch(
            "app.services.news.poll.crud.get_poll_by_news_id", new=AsyncMock(return_value=None)
        ):
            with pytest.raises(HTTPException) as exc_info:
                await delete_poll(db, NEWS_ID)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_deletes_poll(self):
        from app.services.news.poll.crud import delete_poll

        poll = _make_poll()
        db = _make_db()
        with patch(
            "app.services.news.poll.crud.get_poll_by_news_id", new=AsyncMock(return_value=poll)
        ):
            await delete_poll(db, NEWS_ID)
        db.delete.assert_awaited_once_with(poll)
        db.commit.assert_awaited()


class TestClosePoll:
    @pytest.mark.asyncio
    async def test_poll_not_found_raises_404(self):
        from app.services.news.poll.crud import close_poll

        db = _make_db()
        with patch(
            "app.services.news.poll.crud.get_poll_by_news_id", new=AsyncMock(return_value=None)
        ):
            with pytest.raises(HTTPException) as exc_info:
                await close_poll(db, NEWS_ID, NOW)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_closes_poll(self):
        from app.services.news.poll.crud import close_poll

        poll = _make_poll()
        db = _make_db()
        with patch(
            "app.services.news.poll.crud.get_poll_by_news_id", new=AsyncMock(return_value=poll)
        ):
            await close_poll(db, NEWS_ID, NOW)
        assert poll.closed_at == NOW
        db.commit.assert_awaited()


class TestReopenPoll:
    @pytest.mark.asyncio
    async def test_poll_not_found_raises_404(self):
        from app.services.news.poll.crud import reopen_poll

        db = _make_db()
        with patch(
            "app.services.news.poll.crud.get_poll_by_news_id", new=AsyncMock(return_value=None)
        ):
            with pytest.raises(HTTPException) as exc_info:
                await reopen_poll(db, NEWS_ID, NOW)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_reopen_poll_closes_at_passed_raises(self):
        from app.services.news.poll.crud import reopen_poll

        past = datetime(2023, 1, 1, tzinfo=UTC)
        poll = _make_poll(closes_at=past)
        db = _make_db()
        with patch(
            "app.services.news.poll.crud.get_poll_by_news_id", new=AsyncMock(return_value=poll)
        ):
            with pytest.raises(HTTPException) as exc_info:
                await reopen_poll(db, NEWS_ID, NOW)
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_reopen_poll_success(self):
        from app.services.news.poll.crud import reopen_poll

        future = datetime(2025, 1, 1, tzinfo=UTC)
        poll = _make_poll(closed_at=NOW, closes_at=future)
        db = _make_db()
        with patch(
            "app.services.news.poll.crud.get_poll_by_news_id", new=AsyncMock(return_value=poll)
        ):
            await reopen_poll(db, NEWS_ID, NOW)
        assert poll.closed_at is None
        db.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_reopen_poll_no_closes_at_success(self):
        from app.services.news.poll.crud import reopen_poll

        poll = _make_poll(closed_at=NOW, closes_at=None)
        db = _make_db()
        with patch(
            "app.services.news.poll.crud.get_poll_by_news_id", new=AsyncMock(return_value=poll)
        ):
            await reopen_poll(db, NEWS_ID, NOW)
        assert poll.closed_at is None
        db.commit.assert_awaited()
