from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

NOW = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
NEWS_ID = uuid.uuid4()
USER_ID = uuid.uuid4()
POLL_ID = uuid.uuid4()


def _make_db() -> AsyncMock:
    db = AsyncMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.flush = AsyncMock()
    db.add = MagicMock()
    db.delete = AsyncMock()
    db.bind = None
    return db


def _make_option(oid: uuid.UUID | None = None) -> SimpleNamespace:
    o = SimpleNamespace()
    o.id = oid or uuid.uuid4()
    o.votes_count = 0
    return o


def _make_question(
    qid: uuid.UUID | None = None,
    is_required: bool = True,
    is_multiple: bool = False,
    max_choices: int | None = None,
    allow_custom_answer: bool = False,
    options: list | None = None,
) -> SimpleNamespace:
    q = SimpleNamespace()
    q.id = qid or uuid.uuid4()
    q.is_required = is_required
    q.is_multiple = is_multiple
    q.max_choices = max_choices
    q.allow_custom_answer = allow_custom_answer
    q.options = options or [_make_option(), _make_option()]
    return q


def _make_poll(
    poll_id: uuid.UUID | None = None,
    questions: list | None = None,
    allow_revote: bool = False,
    is_anonymous: bool = True,
    results_visibility: str = "after_vote",
    closed_at: datetime | None = None,
    closes_at: datetime | None = None,
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
    return p


def _make_voter(
    voter_id: uuid.UUID | None = None, poll_id: uuid.UUID | None = None
) -> SimpleNamespace:
    v = SimpleNamespace()
    v.id = voter_id or uuid.uuid4()
    v.poll_id = poll_id or POLL_ID
    v.user_id = USER_ID
    v.created_at = NOW
    return v


class TestAcquireVoteLock:
    @pytest.mark.asyncio
    async def test_non_postgres_returns_early(self):
        from app.services.news.poll.voting import _acquire_vote_lock

        db = _make_db()
        db.bind = MagicMock()
        db.bind.dialect.name = "sqlite"
        await _acquire_vote_lock(db, POLL_ID, USER_ID)
        db.execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_none_bind_returns_early(self):
        from app.services.news.poll.voting import _acquire_vote_lock

        db = _make_db()
        db.bind = None
        await _acquire_vote_lock(db, POLL_ID, USER_ID)
        db.execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_postgres_executes_lock(self):
        from app.services.news.poll.voting import _acquire_vote_lock

        db = _make_db()
        db.bind = MagicMock()
        db.bind.dialect.name = "postgresql"
        await _acquire_vote_lock(db, POLL_ID, USER_ID)
        db.execute.assert_awaited_once()


class TestValidateAnswers:
    def _make_answer(self, question_id, option_ids=None, custom_text=None):
        from app.schemas.news_poll import NewsPollAnswer

        return NewsPollAnswer(
            question_id=question_id,
            option_ids=option_ids or [],
            custom_text=custom_text,
        )

    def test_valid_single_choice(self):
        from app.services.news.poll.voting import _validate_answers

        opt = _make_option()
        q = _make_question(is_required=True, is_multiple=False, options=[opt, _make_option()])
        poll = _make_poll(questions=[q])
        ans = self._make_answer(q.id, option_ids=[opt.id])
        _validate_answers(poll, [ans])

    def test_duplicate_question_raises(self):
        from app.services.news.poll.voting import _validate_answers

        opt = _make_option()
        q = _make_question(options=[opt, _make_option()])
        poll = _make_poll(questions=[q])
        ans = self._make_answer(q.id, option_ids=[opt.id])
        with pytest.raises(HTTPException) as exc_info:
            _validate_answers(poll, [ans, ans])
        assert exc_info.value.status_code == 400

    def test_unknown_question_raises_422(self):
        from app.services.news.poll.voting import _validate_answers

        poll = _make_poll(questions=[])
        ans = self._make_answer(uuid.uuid4(), option_ids=[uuid.uuid4()])
        with pytest.raises(HTTPException) as exc_info:
            _validate_answers(poll, [ans])
        assert exc_info.value.status_code == 422

    def test_required_question_not_answered_raises(self):
        from app.services.news.poll.voting import _validate_answers

        q = _make_question(is_required=True)
        poll = _make_poll(questions=[q])
        with pytest.raises(HTTPException) as exc_info:
            _validate_answers(poll, [])
        assert exc_info.value.status_code == 400

    def test_optional_question_no_answer_ok(self):
        from app.services.news.poll.voting import _validate_answers

        q = _make_question(is_required=False)
        poll = _make_poll(questions=[q])
        ans = self._make_answer(q.id)
        _validate_answers(poll, [ans])

    def test_custom_text_not_allowed_raises(self):
        from app.services.news.poll.voting import _validate_answers

        q = _make_question(is_required=False, allow_custom_answer=False)
        poll = _make_poll(questions=[q])
        ans = self._make_answer(q.id, custom_text="free text")
        with pytest.raises(HTTPException) as exc_info:
            _validate_answers(poll, [ans])
        assert exc_info.value.status_code == 400

    def test_invalid_option_id_raises_422(self):
        from app.services.news.poll.voting import _validate_answers

        opt1 = _make_option()
        opt2 = _make_option()
        q = _make_question(is_required=True, options=[opt1, opt2])
        poll = _make_poll(questions=[q])
        ans = self._make_answer(q.id, option_ids=[uuid.uuid4()])
        with pytest.raises(HTTPException) as exc_info:
            _validate_answers(poll, [ans])
        assert exc_info.value.status_code == 422

    def test_duplicate_option_ids_raises(self):
        from app.services.news.poll.voting import _validate_answers

        opt = _make_option()
        q = _make_question(is_required=True, options=[opt, _make_option()])
        poll = _make_poll(questions=[q])
        ans = self._make_answer(q.id, option_ids=[opt.id, opt.id])
        with pytest.raises(HTTPException) as exc_info:
            _validate_answers(poll, [ans])
        assert exc_info.value.status_code == 400

    def test_single_choice_multiple_picks_raises(self):
        from app.services.news.poll.voting import _validate_answers

        opt1 = _make_option()
        opt2 = _make_option()
        q = _make_question(is_required=True, is_multiple=False, options=[opt1, opt2])
        poll = _make_poll(questions=[q])
        ans = self._make_answer(q.id, option_ids=[opt1.id, opt2.id])
        with pytest.raises(HTTPException) as exc_info:
            _validate_answers(poll, [ans])
        assert exc_info.value.status_code == 400

    def test_max_choices_exceeded_raises_409(self):
        from app.services.news.poll.voting import _validate_answers

        opt1 = _make_option()
        opt2 = _make_option()
        opt3 = _make_option()
        q = _make_question(
            is_required=True, is_multiple=True, max_choices=2, options=[opt1, opt2, opt3]
        )
        poll = _make_poll(questions=[q])
        ans = self._make_answer(q.id, option_ids=[opt1.id, opt2.id, opt3.id])
        with pytest.raises(HTTPException) as exc_info:
            _validate_answers(poll, [ans])
        assert exc_info.value.status_code == 409

    def test_multiple_choice_within_max_ok(self):
        from app.services.news.poll.voting import _validate_answers

        opt1 = _make_option()
        opt2 = _make_option()
        q = _make_question(is_required=True, is_multiple=True, max_choices=3, options=[opt1, opt2])
        poll = _make_poll(questions=[q])
        ans = self._make_answer(q.id, option_ids=[opt1.id, opt2.id])
        _validate_answers(poll, [ans])

    def test_required_question_skipped_raises(self):
        from app.services.news.poll.voting import _validate_answers

        q1 = _make_question(is_required=True)
        q2 = _make_question(is_required=False)
        poll = _make_poll(questions=[q1, q2])
        with pytest.raises(HTTPException) as exc_info:
            _validate_answers(poll, [])
        assert exc_info.value.status_code == 400

    def test_custom_text_and_option_single_choice_ok(self):
        from app.services.news.poll.voting import _validate_answers

        opt = _make_option()
        q = _make_question(
            is_required=True,
            is_multiple=False,
            allow_custom_answer=True,
            options=[opt, _make_option()],
        )
        poll = _make_poll(questions=[q])
        ans = self._make_answer(q.id, custom_text="text")
        _validate_answers(poll, [ans])


class TestRecomputeOptionCounts:
    @pytest.mark.asyncio
    async def test_recomputes_correctly(self):
        from app.services.news.poll.voting import _recompute_option_counts

        opt_id = uuid.uuid4()
        opt = _make_option(opt_id)
        opt.votes_count = 0

        result_counts = MagicMock()
        result_counts.all.return_value = [(opt_id, 3)]

        result_options = MagicMock()
        result_options.scalars.return_value.all.return_value = [opt]

        db = _make_db()
        db.execute = AsyncMock(side_effect=[result_counts, result_options])

        await _recompute_option_counts(db, POLL_ID)
        assert opt.votes_count == 3

    @pytest.mark.asyncio
    async def test_option_with_no_votes_set_to_zero(self):
        from app.services.news.poll.voting import _recompute_option_counts

        opt = _make_option()
        opt.votes_count = 5

        result_counts = MagicMock()
        result_counts.all.return_value = []

        result_options = MagicMock()
        result_options.scalars.return_value.all.return_value = [opt]

        db = _make_db()
        db.execute = AsyncMock(side_effect=[result_counts, result_options])

        await _recompute_option_counts(db, POLL_ID)
        assert opt.votes_count == 0


class TestCastVote:
    def _make_answer(self, question_id, option_ids=None, custom_text=None):
        from app.schemas.news_poll import NewsPollAnswer

        return NewsPollAnswer(
            question_id=question_id,
            option_ids=option_ids or [],
            custom_text=custom_text,
        )

    @pytest.mark.asyncio
    async def test_poll_not_found_raises_404(self):
        from app.services.news.poll.voting import cast_vote

        db = _make_db()
        with (
            patch(
                "app.services.news.poll.voting.get_poll_by_news_id",
                new=AsyncMock(return_value=None),
            ),
            pytest.raises(HTTPException) as exc_info,
        ):
            await cast_vote(db, NEWS_ID, USER_ID, [], NOW)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_poll_closed_raises_409(self):
        from app.services.news.poll.voting import cast_vote

        poll = _make_poll(closed_at=NOW)
        db = _make_db()
        with (
            patch(
                "app.services.news.poll.voting.get_poll_by_news_id",
                new=AsyncMock(return_value=poll),
            ),
            patch("app.services.news.poll.voting.is_poll_closed", return_value=True),
            pytest.raises(HTTPException) as exc_info,
        ):
            await cast_vote(db, NEWS_ID, USER_ID, [], NOW)
        assert exc_info.value.status_code == 409

    @pytest.mark.asyncio
    async def test_already_voted_no_revote_raises_409(self):
        from app.services.news.poll.voting import cast_vote

        opt = _make_option()
        q = _make_question(is_required=True, options=[opt, _make_option()])
        poll = _make_poll(questions=[q], allow_revote=False)
        voter = _make_voter(poll_id=poll.id)

        ans = self._make_answer(q.id, option_ids=[opt.id])

        result_voter = MagicMock()
        result_voter.scalar_one_or_none.return_value = voter

        db = _make_db()
        db.execute = AsyncMock(return_value=result_voter)

        with (
            patch(
                "app.services.news.poll.voting.get_poll_by_news_id",
                new=AsyncMock(return_value=poll),
            ),
            patch("app.services.news.poll.voting.is_poll_closed", return_value=False),
            patch("app.services.news.poll.voting._acquire_vote_lock", new=AsyncMock()),
            pytest.raises(HTTPException) as exc_info,
        ):
            await cast_vote(db, NEWS_ID, USER_ID, [ans], NOW)
        assert exc_info.value.status_code == 409

    @pytest.mark.asyncio
    async def test_new_voter_casts_vote(self):
        from app.services.news.poll.voting import cast_vote

        opt = _make_option()
        q = _make_question(is_required=True, options=[opt, _make_option()])
        poll = _make_poll(questions=[q], allow_revote=False)

        ans = self._make_answer(q.id, option_ids=[opt.id])

        result_voter = MagicMock()
        result_voter.scalar_one_or_none.return_value = None

        result_counts = MagicMock()
        result_counts.all.return_value = [(opt.id, 1)]

        result_options = MagicMock()
        result_options.scalars.return_value.all.return_value = [opt]

        db = _make_db()
        db.execute = AsyncMock(side_effect=[result_voter, result_counts, result_options])
        db.flush = AsyncMock()

        with (
            patch(
                "app.services.news.poll.voting.get_poll_by_news_id",
                new=AsyncMock(return_value=poll),
            ),
            patch("app.services.news.poll.voting.is_poll_closed", return_value=False),
            patch("app.services.news.poll.voting._acquire_vote_lock", new=AsyncMock()),
        ):
            await cast_vote(db, NEWS_ID, USER_ID, [ans], NOW)

        db.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_revote_deletes_previous_votes(self):
        from app.services.news.poll.voting import cast_vote

        opt = _make_option()
        q = _make_question(is_required=True, options=[opt, _make_option()])
        poll = _make_poll(questions=[q], allow_revote=True)
        voter = _make_voter(poll_id=poll.id)

        ans = self._make_answer(q.id, option_ids=[opt.id])

        result_voter = MagicMock()
        result_voter.scalar_one_or_none.return_value = voter

        result_delete = MagicMock()

        result_counts = MagicMock()
        result_counts.all.return_value = [(opt.id, 1)]

        result_options = MagicMock()
        result_options.scalars.return_value.all.return_value = [opt]

        db = _make_db()
        db.execute = AsyncMock(
            side_effect=[result_voter, result_delete, result_counts, result_options]
        )

        with (
            patch(
                "app.services.news.poll.voting.get_poll_by_news_id",
                new=AsyncMock(return_value=poll),
            ),
            patch("app.services.news.poll.voting.is_poll_closed", return_value=False),
            patch("app.services.news.poll.voting._acquire_vote_lock", new=AsyncMock()),
        ):
            await cast_vote(db, NEWS_ID, USER_ID, [ans], NOW)

        db.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_cast_vote_with_custom_text(self):
        from app.services.news.poll.voting import cast_vote

        q = _make_question(is_required=True, is_multiple=False, allow_custom_answer=True)
        poll = _make_poll(questions=[q], allow_revote=False)

        ans = self._make_answer(q.id, custom_text="my answer")

        result_voter = MagicMock()
        result_voter.scalar_one_or_none.return_value = None

        result_counts = MagicMock()
        result_counts.all.return_value = []

        result_options = MagicMock()
        result_options.scalars.return_value.all.return_value = []

        db = _make_db()
        db.execute = AsyncMock(side_effect=[result_voter, result_counts, result_options])

        with (
            patch(
                "app.services.news.poll.voting.get_poll_by_news_id",
                new=AsyncMock(return_value=poll),
            ),
            patch("app.services.news.poll.voting.is_poll_closed", return_value=False),
            patch("app.services.news.poll.voting._acquire_vote_lock", new=AsyncMock()),
        ):
            await cast_vote(db, NEWS_ID, USER_ID, [ans], NOW)

        db.commit.assert_awaited()


class TestRevokeVote:
    @pytest.mark.asyncio
    async def test_poll_not_found_raises_404(self):
        from app.services.news.poll.voting import revoke_vote

        db = _make_db()
        with (
            patch(
                "app.services.news.poll.voting.get_poll_by_news_id",
                new=AsyncMock(return_value=None),
            ),
            pytest.raises(HTTPException) as exc_info,
        ):
            await revoke_vote(db, NEWS_ID, USER_ID, NOW)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_poll_closed_raises_409(self):
        from app.services.news.poll.voting import revoke_vote

        poll = _make_poll()
        db = _make_db()
        with (
            patch(
                "app.services.news.poll.voting.get_poll_by_news_id",
                new=AsyncMock(return_value=poll),
            ),
            patch("app.services.news.poll.voting.is_poll_closed", return_value=True),
            pytest.raises(HTTPException) as exc_info,
        ):
            await revoke_vote(db, NEWS_ID, USER_ID, NOW)
        assert exc_info.value.status_code == 409

    @pytest.mark.asyncio
    async def test_revote_not_allowed_raises_409(self):
        from app.services.news.poll.voting import revoke_vote

        poll = _make_poll(allow_revote=False)
        db = _make_db()
        with (
            patch(
                "app.services.news.poll.voting.get_poll_by_news_id",
                new=AsyncMock(return_value=poll),
            ),
            patch("app.services.news.poll.voting.is_poll_closed", return_value=False),
            pytest.raises(HTTPException) as exc_info,
        ):
            await revoke_vote(db, NEWS_ID, USER_ID, NOW)
        assert exc_info.value.status_code == 409

    @pytest.mark.asyncio
    async def test_voter_not_found_raises_404(self):
        from app.services.news.poll.voting import revoke_vote

        poll = _make_poll(allow_revote=True)
        result_voter = MagicMock()
        result_voter.scalar_one_or_none.return_value = None

        db = _make_db()
        db.execute = AsyncMock(return_value=result_voter)

        with (
            patch(
                "app.services.news.poll.voting.get_poll_by_news_id",
                new=AsyncMock(return_value=poll),
            ),
            patch("app.services.news.poll.voting.is_poll_closed", return_value=False),
            patch("app.services.news.poll.voting._acquire_vote_lock", new=AsyncMock()),
            pytest.raises(HTTPException) as exc_info,
        ):
            await revoke_vote(db, NEWS_ID, USER_ID, NOW)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_successful_revoke(self):
        from app.services.news.poll.voting import revoke_vote

        poll = _make_poll(allow_revote=True)
        voter = _make_voter(poll_id=poll.id)

        result_voter = MagicMock()
        result_voter.scalar_one_or_none.return_value = voter

        result_counts = MagicMock()
        result_counts.all.return_value = []

        result_options = MagicMock()
        result_options.scalars.return_value.all.return_value = []

        db = _make_db()
        db.execute = AsyncMock(side_effect=[result_voter, result_counts, result_options])

        with (
            patch(
                "app.services.news.poll.voting.get_poll_by_news_id",
                new=AsyncMock(return_value=poll),
            ),
            patch("app.services.news.poll.voting.is_poll_closed", return_value=False),
            patch("app.services.news.poll.voting._acquire_vote_lock", new=AsyncMock()),
        ):
            await revoke_vote(db, NEWS_ID, USER_ID, NOW)

        db.delete.assert_awaited_once_with(voter)
        db.commit.assert_awaited()
