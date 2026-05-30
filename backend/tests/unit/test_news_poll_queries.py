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
    return db


def _make_user(role: str = "reader", uid: uuid.UUID | None = None) -> SimpleNamespace:
    u = SimpleNamespace()
    u.id = uid or uuid.uuid4()
    u.role = role
    u.full_name = "Test User"
    u.email = "test@example.com"
    return u


def _make_option(
    oid: uuid.UUID | None = None, sort_order: int = 0, votes_count: int = 0
) -> SimpleNamespace:
    o = SimpleNamespace()
    o.id = oid or uuid.uuid4()
    o.text = "Option"
    o.image_url = None
    o.sort_order = sort_order
    o.votes_count = votes_count
    return o


def _make_question(
    qid: uuid.UUID | None = None,
    sort_order: int = 0,
    options: list | None = None,
) -> SimpleNamespace:
    q = SimpleNamespace()
    q.id = qid or uuid.uuid4()
    q.text = "Question?"
    q.sort_order = sort_order
    q.is_required = True
    q.is_multiple = False
    q.max_choices = None
    q.allow_custom_answer = False
    q.options = options or [_make_option()]
    return q


def _make_poll(
    poll_id: uuid.UUID | None = None,
    questions: list | None = None,
    is_anonymous: bool = False,
    allow_revote: bool = False,
    results_visibility: str = "always",
    closed_at: datetime | None = None,
    closes_at: datetime | None = None,
) -> SimpleNamespace:
    p = SimpleNamespace()
    p.id = poll_id or uuid.uuid4()
    p.news_id = NEWS_ID
    p.questions = questions or [_make_question()]
    p.is_anonymous = is_anonymous
    p.allow_revote = allow_revote
    p.results_visibility = results_visibility
    p.closed_at = closed_at
    p.closes_at = closes_at
    return p


def _make_vote(
    question_id: uuid.UUID,
    option_id: uuid.UUID | None = None,
    custom_text: str | None = None,
    voter_id: uuid.UUID | None = None,
) -> SimpleNamespace:
    v = SimpleNamespace()
    v.id = uuid.uuid4()
    v.question_id = question_id
    v.option_id = option_id
    v.custom_text = custom_text
    v.voter_id = voter_id or uuid.uuid4()
    v.poll_id = POLL_ID
    return v


def _make_voter(user_id: uuid.UUID | None = None, votes: list | None = None) -> SimpleNamespace:
    voter = SimpleNamespace()
    voter.id = uuid.uuid4()
    voter.poll_id = POLL_ID
    voter.user_id = user_id or uuid.uuid4()
    voter.created_at = NOW
    voter.votes = votes or []
    voter.user = _make_user()
    return voter


class TestGetPollByNewsId:
    @pytest.mark.asyncio
    async def test_returns_poll_when_found(self):
        from app.services.news.poll.queries import get_poll_by_news_id

        poll = _make_poll()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = poll

        db = _make_db()
        db.execute = AsyncMock(return_value=result_mock)

        result = await get_poll_by_news_id(db, NEWS_ID)
        assert result is poll

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self):
        from app.services.news.poll.queries import get_poll_by_news_id

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None

        db = _make_db()
        db.execute = AsyncMock(return_value=result_mock)

        result = await get_poll_by_news_id(db, NEWS_ID)
        assert result is None


class TestBuildPollPublicResponse:
    def _make_execute_seq(self, *results):
        mocks = []
        for r in results:
            m = MagicMock()
            m.scalar_one_or_none.return_value = r if not isinstance(r, (int, list)) else None
            m.scalar_one.return_value = r if isinstance(r, int) else 0
            m.all.return_value = r if isinstance(r, list) else []
            mocks.append(m)
        return mocks

    @pytest.mark.asyncio
    async def test_anonymous_user_no_vote(self):
        from app.services.news.poll.queries import build_poll_public_response

        poll = _make_poll(results_visibility="always")
        q = poll.questions[0]
        opt = q.options[0]

        result_total_voters = MagicMock()
        result_total_voters.scalar_one.return_value = 0

        result_qtotals = MagicMock()
        result_qtotals.all.return_value = []

        result_custom = MagicMock()
        result_custom.all.return_value = []

        db = _make_db()
        db.execute = AsyncMock(side_effect=[result_total_voters, result_qtotals, result_custom])

        response = await build_poll_public_response(db, poll, None, NOW)
        assert response.total_voters == 0
        assert response.can_vote is False
        assert response.can_see_results is True
        assert response.my_vote is None

    @pytest.mark.asyncio
    async def test_user_has_voted_with_option(self):
        from app.services.news.poll.queries import build_poll_public_response

        poll = _make_poll(results_visibility="after_vote", allow_revote=True)
        q = poll.questions[0]
        opt = q.options[0]

        user = _make_user()
        voter = _make_voter(user_id=user.id)
        vote = _make_vote(question_id=q.id, option_id=opt.id, voter_id=voter.id)
        voter.votes = [vote]

        result_voter = MagicMock()
        result_voter.scalar_one_or_none.return_value = voter

        result_total_voters = MagicMock()
        result_total_voters.scalar_one.return_value = 1

        result_qtotals = MagicMock()
        result_qtotals.all.return_value = [(q.id, 1)]

        result_custom = MagicMock()
        result_custom.all.return_value = []

        db = _make_db()
        db.execute = AsyncMock(
            side_effect=[result_voter, result_total_voters, result_qtotals, result_custom]
        )

        response = await build_poll_public_response(db, poll, user, NOW)
        assert response.my_vote is not None
        assert response.can_vote is True
        assert response.can_see_results is True
        assert len(response.my_vote.answers) == 1
        assert response.my_vote.answers[0].option_ids == [opt.id]

    @pytest.mark.asyncio
    async def test_user_has_voted_with_custom_text(self):
        from app.services.news.poll.queries import build_poll_public_response

        poll = _make_poll(results_visibility="after_vote")
        q = poll.questions[0]

        user = _make_user()
        voter = _make_voter(user_id=user.id)
        vote = _make_vote(question_id=q.id, custom_text="my text", voter_id=voter.id)
        voter.votes = [vote]

        result_voter = MagicMock()
        result_voter.scalar_one_or_none.return_value = voter

        result_total_voters = MagicMock()
        result_total_voters.scalar_one.return_value = 1

        result_qtotals = MagicMock()
        result_qtotals.all.return_value = [(q.id, 1)]

        result_custom = MagicMock()
        result_custom.all.return_value = []

        db = _make_db()
        db.execute = AsyncMock(
            side_effect=[result_voter, result_total_voters, result_qtotals, result_custom]
        )

        response = await build_poll_public_response(db, poll, user, NOW)
        assert response.my_vote is not None
        assert response.my_vote.answers[0].custom_text == "my text"

    @pytest.mark.asyncio
    async def test_poll_closed_user_can_not_vote(self):
        from app.services.news.poll.queries import build_poll_public_response

        poll = _make_poll(results_visibility="always", closed_at=NOW)
        user = _make_user()

        result_voter = MagicMock()
        result_voter.scalar_one_or_none.return_value = None

        result_total_voters = MagicMock()
        result_total_voters.scalar_one.return_value = 5

        result_qtotals = MagicMock()
        result_qtotals.all.return_value = []

        result_custom = MagicMock()
        result_custom.all.return_value = []

        db = _make_db()
        db.execute = AsyncMock(
            side_effect=[result_voter, result_total_voters, result_qtotals, result_custom]
        )

        response = await build_poll_public_response(db, poll, user, NOW)
        assert response.can_vote is False
        assert response.is_closed is True

    @pytest.mark.asyncio
    async def test_after_close_visibility_not_closed(self):
        from app.services.news.poll.queries import build_poll_public_response

        poll = _make_poll(results_visibility="after_close")
        user = _make_user()

        result_voter = MagicMock()
        result_voter.scalar_one_or_none.return_value = None

        result_total_voters = MagicMock()
        result_total_voters.scalar_one.return_value = 0

        db = _make_db()
        db.execute = AsyncMock(side_effect=[result_voter, result_total_voters])

        response = await build_poll_public_response(db, poll, user, NOW)
        assert response.can_see_results is False
        assert response.total_voters is None

    @pytest.mark.asyncio
    async def test_admin_can_always_see_results(self):
        from app.services.news.poll.queries import build_poll_public_response

        poll = _make_poll(results_visibility="only_admin_editor")
        admin = _make_user(role="admin")

        result_voter = MagicMock()
        result_voter.scalar_one_or_none.return_value = None

        result_total_voters = MagicMock()
        result_total_voters.scalar_one.return_value = 10

        result_qtotals = MagicMock()
        result_qtotals.all.return_value = []

        result_custom = MagicMock()
        result_custom.all.return_value = []

        db = _make_db()
        db.execute = AsyncMock(
            side_effect=[result_voter, result_total_voters, result_qtotals, result_custom]
        )

        response = await build_poll_public_response(db, poll, admin, NOW)
        assert response.can_see_results is True
        assert response.total_voters == 10

    @pytest.mark.asyncio
    async def test_option_votes_percent_computed(self):
        from app.services.news.poll.queries import build_poll_public_response

        q = _make_question()
        opt = _make_option(oid=uuid.uuid4(), votes_count=2)
        q.options = [opt]
        poll = _make_poll(questions=[q], results_visibility="always")

        result_total_voters = MagicMock()
        result_total_voters.scalar_one.return_value = 2

        result_qtotals = MagicMock()
        result_qtotals.all.return_value = [(q.id, 2)]

        result_custom = MagicMock()
        result_custom.all.return_value = []

        db = _make_db()
        db.execute = AsyncMock(side_effect=[result_total_voters, result_qtotals, result_custom])

        response = await build_poll_public_response(db, poll, None, NOW)
        assert response.questions[0].options[0].votes_count == 2
        assert response.questions[0].options[0].votes_percent == 100.0

    @pytest.mark.asyncio
    async def test_option_percent_zero_when_no_answers(self):
        from app.services.news.poll.queries import build_poll_public_response

        q = _make_question()
        opt = _make_option(oid=uuid.uuid4(), votes_count=0)
        q.options = [opt]
        poll = _make_poll(questions=[q], results_visibility="always")

        result_total_voters = MagicMock()
        result_total_voters.scalar_one.return_value = 0

        result_qtotals = MagicMock()
        result_qtotals.all.return_value = []

        result_custom = MagicMock()
        result_custom.all.return_value = []

        db = _make_db()
        db.execute = AsyncMock(side_effect=[result_total_voters, result_qtotals, result_custom])

        response = await build_poll_public_response(db, poll, None, NOW)
        assert response.questions[0].options[0].votes_percent == 0.0

    @pytest.mark.asyncio
    async def test_anonymous_poll_hides_voter_id_for_reader(self):
        from app.services.news.poll.queries import build_poll_public_response

        q = _make_question()
        poll = _make_poll(questions=[q], is_anonymous=True, results_visibility="always")
        user = _make_user(role="reader")

        result_voter = MagicMock()
        result_voter.scalar_one_or_none.return_value = None

        result_total_voters = MagicMock()
        result_total_voters.scalar_one.return_value = 1

        result_qtotals = MagicMock()
        result_qtotals.all.return_value = [(q.id, 1)]

        voter_obj = _make_voter()
        vote_obj = _make_vote(question_id=q.id, custom_text="anon answer")
        voter_obj.user = _make_user()

        result_custom = MagicMock()
        result_custom.all.return_value = [(vote_obj, voter_obj)]

        db = _make_db()
        db.execute = AsyncMock(
            side_effect=[result_voter, result_total_voters, result_qtotals, result_custom]
        )

        response = await build_poll_public_response(db, poll, user, NOW)
        custom_answers = response.questions[0].custom_answers
        assert custom_answers is not None
        assert custom_answers[0].voter_id is None
        assert custom_answers[0].voter_name is None

    @pytest.mark.asyncio
    async def test_non_anonymous_poll_shows_voter_id_for_reader(self):
        from app.services.news.poll.queries import build_poll_public_response

        q = _make_question()
        poll = _make_poll(questions=[q], is_anonymous=False, results_visibility="always")
        user = _make_user(role="reader")

        result_voter = MagicMock()
        result_voter.scalar_one_or_none.return_value = None

        result_total_voters = MagicMock()
        result_total_voters.scalar_one.return_value = 1

        result_qtotals = MagicMock()
        result_qtotals.all.return_value = [(q.id, 1)]

        voter_user = _make_user()
        voter_obj = _make_voter(user_id=voter_user.id)
        voter_obj.user = voter_user
        vote_obj = _make_vote(question_id=q.id, custom_text="public answer")

        result_custom = MagicMock()
        result_custom.all.return_value = [(vote_obj, voter_obj)]

        db = _make_db()
        db.execute = AsyncMock(
            side_effect=[result_voter, result_total_voters, result_qtotals, result_custom]
        )

        response = await build_poll_public_response(db, poll, user, NOW)
        custom_answers = response.questions[0].custom_answers
        assert custom_answers is not None
        assert custom_answers[0].voter_id == voter_user.id

    @pytest.mark.asyncio
    async def test_user_not_voted_no_revote_cannot_vote(self):
        from app.services.news.poll.queries import build_poll_public_response

        poll = _make_poll(results_visibility="after_vote", allow_revote=False)
        user = _make_user()

        result_voter = MagicMock()
        result_voter.scalar_one_or_none.return_value = None

        result_total_voters = MagicMock()
        result_total_voters.scalar_one.return_value = 0

        db = _make_db()
        db.execute = AsyncMock(side_effect=[result_voter, result_total_voters])

        response = await build_poll_public_response(db, poll, user, NOW)
        assert response.can_vote is True
        assert response.can_see_results is False


class TestGetVotersList:
    @pytest.mark.asyncio
    async def test_poll_not_found_raises_404(self):
        from app.services.news.poll.queries import get_voters_list

        db = _make_db()
        user = _make_user(role="admin")
        with patch(
            "app.services.news.poll.queries.get_poll_by_news_id", new=AsyncMock(return_value=None)
        ):
            with pytest.raises(HTTPException) as exc_info:
                await get_voters_list(db, NEWS_ID, user=user, now=NOW)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_anonymous_poll_non_privileged_raises_403(self):
        from app.services.news.poll.queries import get_voters_list

        poll = _make_poll(is_anonymous=True)
        db = _make_db()
        user = _make_user(role="reader")
        with patch(
            "app.services.news.poll.queries.get_poll_by_news_id", new=AsyncMock(return_value=poll)
        ):
            with pytest.raises(HTTPException) as exc_info:
                await get_voters_list(db, NEWS_ID, user=user, now=NOW)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_anonymous_poll_admin_allowed(self):
        from app.services.news.poll.queries import get_voters_list

        q = _make_question()
        opt = _make_option()
        q.options = [opt]
        poll = _make_poll(is_anonymous=True, questions=[q])

        user = _make_user(role="admin")
        voter_user = _make_user()
        voter = _make_voter(user_id=voter_user.id)
        voter.user = voter_user

        vote = _make_vote(question_id=q.id, option_id=opt.id, voter_id=voter.id)
        voter.votes = [vote]

        result_voters = MagicMock()
        result_voters.scalars.return_value.all.return_value = [voter]

        db = _make_db()
        db.execute = AsyncMock(return_value=result_voters)

        with patch(
            "app.services.news.poll.queries.get_poll_by_news_id", new=AsyncMock(return_value=poll)
        ):
            result = await get_voters_list(db, NEWS_ID, user=user, now=NOW)

        assert len(result) == 1
        assert result[0]["user"]["id"] == voter_user.id

    @pytest.mark.asyncio
    async def test_non_anonymous_poll_reader_allowed(self):
        from app.services.news.poll.queries import get_voters_list

        q = _make_question()
        opt = _make_option()
        q.options = [opt]
        poll = _make_poll(is_anonymous=False, questions=[q])

        user = _make_user(role="reader")
        voter_user = _make_user()
        voter = _make_voter(user_id=voter_user.id)
        voter.user = voter_user

        vote = _make_vote(question_id=q.id, option_id=opt.id, voter_id=voter.id)
        voter.votes = [vote]

        result_voters = MagicMock()
        result_voters.scalars.return_value.all.return_value = [voter]

        db = _make_db()
        db.execute = AsyncMock(return_value=result_voters)

        with patch(
            "app.services.news.poll.queries.get_poll_by_news_id", new=AsyncMock(return_value=poll)
        ):
            result = await get_voters_list(db, NEWS_ID, user=user, now=NOW)

        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_voter_without_user_skipped(self):
        from app.services.news.poll.queries import get_voters_list

        poll = _make_poll(is_anonymous=False)
        user = _make_user(role="reader")

        voter = _make_voter()
        voter.user = None
        voter.votes = []

        result_voters = MagicMock()
        result_voters.scalars.return_value.all.return_value = [voter]

        db = _make_db()
        db.execute = AsyncMock(return_value=result_voters)

        with patch(
            "app.services.news.poll.queries.get_poll_by_news_id", new=AsyncMock(return_value=poll)
        ):
            result = await get_voters_list(db, NEWS_ID, user=user, now=NOW)

        assert result == []

    @pytest.mark.asyncio
    async def test_voter_with_custom_text_answer(self):
        from app.services.news.poll.queries import get_voters_list

        q = _make_question()
        poll = _make_poll(is_anonymous=False, questions=[q])

        user = _make_user(role="reader")
        voter_user = _make_user()
        voter = _make_voter(user_id=voter_user.id)
        voter.user = voter_user

        vote = _make_vote(question_id=q.id, custom_text="free text", voter_id=voter.id)
        voter.votes = [vote]

        result_voters = MagicMock()
        result_voters.scalars.return_value.all.return_value = [voter]

        db = _make_db()
        db.execute = AsyncMock(return_value=result_voters)

        with patch(
            "app.services.news.poll.queries.get_poll_by_news_id", new=AsyncMock(return_value=poll)
        ):
            result = await get_voters_list(db, NEWS_ID, user=user, now=NOW)

        assert result[0]["answers"][0]["custom_text"] == "free text"

    @pytest.mark.asyncio
    async def test_empty_voters_list(self):
        from app.services.news.poll.queries import get_voters_list

        poll = _make_poll(is_anonymous=False)
        user = _make_user(role="reader")

        result_voters = MagicMock()
        result_voters.scalars.return_value.all.return_value = []

        db = _make_db()
        db.execute = AsyncMock(return_value=result_voters)

        with patch(
            "app.services.news.poll.queries.get_poll_by_news_id", new=AsyncMock(return_value=poll)
        ):
            result = await get_voters_list(db, NEWS_ID, user=user, now=NOW)

        assert result == []
