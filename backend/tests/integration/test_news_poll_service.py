"""Integration tests for ``app.services.news.poll``.

Покрывает:
- create_poll: happy path, дубликат, missing news
- update_poll: ALWAYS_EDITABLE/FROZEN_AFTER_VOTE для poll и question, опции
- close_poll / reopen_poll: переключение closed_at, запрет reopen после closes_at
- delete_poll
- cast_vote: одиночный/множественный/custom-text, ревот, валидация ответов
- revoke_vote: happy + запреты
- get_voters_list: privileged vs anonymous
- build_poll_public_response: видимость результатов, anonymous fields, my_vote
- helpers: is_poll_closed, _can_see_results
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.models.news import (
    News,
    NewsPoll,
    NewsPollVote,
    NewsPollVoter,
)
from app.schemas.news_poll import (
    CreateNewsPollOption,
    CreateNewsPollQuestion,
    CreateNewsPollRequest,
    NewsPollAnswer,
    UpdateNewsPollOption,
    UpdateNewsPollQuestion,
    UpdateNewsPollRequest,
)
from app.services.news.poll import (
    _can_see_results,
    build_poll_public_response,
    cast_vote,
    close_poll,
    create_poll,
    delete_poll,
    get_poll_by_news_id,
    get_voters_list,
    is_poll_closed,
    reopen_poll,
    revoke_vote,
    update_poll,
)

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


# ── helpers ──────────────────────────────────────────────────────────────────


async def _make_news(db, author) -> News:
    news = News(
        title="poll-news",
        body="<p>x</p>",
        status="published",
        is_pinned=False,
        categories=[],
        author_id=author.id,
        current_version=1,
        published_at=NOW,
    )
    db.add(news)
    await db.flush()
    return news


def _simple_create_request(
    *,
    is_anonymous: bool = True,
    allow_revote: bool = False,
    results_visibility: str = "always",
    closes_at: datetime | None = None,
    is_multiple: bool = False,
    allow_custom_answer: bool = False,
    is_required: bool = True,
    max_choices: int | None = None,
) -> CreateNewsPollRequest:
    return CreateNewsPollRequest(
        is_anonymous=is_anonymous,
        allow_revote=allow_revote,
        results_visibility=results_visibility,
        closes_at=closes_at,
        questions=[
            CreateNewsPollQuestion(
                text="Q1",
                is_required=is_required,
                is_multiple=is_multiple,
                max_choices=max_choices,
                allow_custom_answer=allow_custom_answer,
                options=[
                    CreateNewsPollOption(text="A", sort_order=0),
                    CreateNewsPollOption(text="B", sort_order=1),
                    CreateNewsPollOption(text="C", sort_order=2),
                ],
            )
        ],
    )


# ── helpers / pure ───────────────────────────────────────────────────────────


def test_is_poll_closed_branches():
    poll = NewsPoll(
        news_id=uuid.uuid4(),
        is_anonymous=True,
        allow_revote=False,
        results_visibility="always",
    )
    assert is_poll_closed(poll, NOW) is False

    poll.closes_at = NOW + timedelta(hours=1)
    assert is_poll_closed(poll, NOW) is False

    poll.closes_at = NOW - timedelta(hours=1)
    assert is_poll_closed(poll, NOW) is True

    poll.closes_at = None
    poll.closed_at = NOW
    assert is_poll_closed(poll, NOW) is True

    # naive datetime — _aware() must coerce
    poll.closed_at = None
    poll.closes_at = (NOW - timedelta(hours=1)).replace(tzinfo=None)
    assert is_poll_closed(poll, NOW) is True


def test_can_see_results_matrix(real_admin_obj=None):
    class _U:
        def __init__(self, role):
            self.role = role

    poll = NewsPoll(
        news_id=uuid.uuid4(),
        is_anonymous=True,
        allow_revote=False,
        results_visibility="always",
    )
    assert _can_see_results(poll, None, has_voted=False, is_closed=False) is True

    poll.results_visibility = "after_vote"
    assert _can_see_results(poll, _U("reader"), has_voted=False, is_closed=False) is False
    assert _can_see_results(poll, _U("reader"), has_voted=True, is_closed=False) is True

    poll.results_visibility = "after_close"
    assert _can_see_results(poll, _U("reader"), has_voted=True, is_closed=False) is False
    assert _can_see_results(poll, _U("reader"), has_voted=False, is_closed=True) is True

    poll.results_visibility = "only_admin_editor"
    assert _can_see_results(poll, _U("reader"), has_voted=True, is_closed=True) is False
    assert _can_see_results(poll, _U("admin"), has_voted=False, is_closed=False) is True
    assert _can_see_results(poll, _U("editor"), has_voted=False, is_closed=False) is True

    poll.results_visibility = "unknown"
    assert _can_see_results(poll, _U("reader"), has_voted=True, is_closed=True) is False


# ── create_poll ──────────────────────────────────────────────────────────────


async def test_create_poll_persists(real_db_session, real_editor):
    news = await _make_news(real_db_session, real_editor)
    poll = await create_poll(real_db_session, news.id, _simple_create_request())
    assert poll.id is not None
    assert poll.news_id == news.id
    assert len(poll.questions) == 1
    assert len(poll.questions[0].options) == 3
    sort_orders = sorted(o.sort_order for o in poll.questions[0].options)
    assert sort_orders == [0, 1, 2]


async def test_create_poll_news_not_found(real_db_session, real_editor):
    with pytest.raises(HTTPException) as exc:
        await create_poll(real_db_session, uuid.uuid4(), _simple_create_request())
    assert exc.value.status_code == 404


async def test_create_poll_duplicate_rejected(real_db_session, real_editor):
    news = await _make_news(real_db_session, real_editor)
    await create_poll(real_db_session, news.id, _simple_create_request())
    with pytest.raises(HTTPException) as exc:
        await create_poll(real_db_session, news.id, _simple_create_request())
    assert exc.value.status_code == 400


# ── update_poll ──────────────────────────────────────────────────────────────


async def test_update_poll_settings_unrestricted(real_db_session, real_editor):
    news = await _make_news(real_db_session, real_editor)
    poll = await create_poll(real_db_session, news.id, _simple_create_request())

    new_close = NOW + timedelta(days=1)
    updated = await update_poll(
        real_db_session,
        news.id,
        UpdateNewsPollRequest(
            is_anonymous=False,
            allow_revote=True,
            results_visibility="after_close",
            closes_at=new_close,
        ),
    )
    assert updated.is_anonymous is False
    assert updated.allow_revote is True
    assert updated.results_visibility == "after_close"
    assert updated.closes_at == new_close
    _ = poll


async def test_update_poll_frozen_after_vote_rejected(real_db_session, real_editor, real_user):
    news = await _make_news(real_db_session, real_editor)
    poll = await create_poll(
        real_db_session,
        news.id,
        _simple_create_request(results_visibility="always"),
    )
    qid = poll.questions[0].id
    oid = poll.questions[0].options[0].id

    await cast_vote(
        real_db_session,
        news.id,
        real_user.id,
        [NewsPollAnswer(question_id=qid, option_ids=[oid])],
        NOW,
    )

    # closes_at — ALWAYS_EDITABLE, OK
    ok = await update_poll(
        real_db_session,
        news.id,
        UpdateNewsPollRequest(closes_at=NOW + timedelta(days=2)),
    )
    assert ok.closes_at == NOW + timedelta(days=2)

    # is_anonymous — FROZEN_AFTER_VOTE, must raise
    with pytest.raises(HTTPException) as exc:
        await update_poll(
            real_db_session,
            news.id,
            UpdateNewsPollRequest(is_anonymous=False),
        )
    assert exc.value.status_code == 403


async def test_update_poll_question_options_unlocked(real_db_session, real_editor):
    news = await _make_news(real_db_session, real_editor)
    poll = await create_poll(real_db_session, news.id, _simple_create_request())
    q = poll.questions[0]
    keep = q.options[0]
    drop_id = q.options[1].id
    rename = q.options[2]

    await update_poll(
        real_db_session,
        news.id,
        UpdateNewsPollRequest(
            questions=[
                UpdateNewsPollQuestion(
                    id=q.id,
                    text="Q1-renamed",
                    options=[
                        UpdateNewsPollOption(id=keep.id, text="A"),
                        UpdateNewsPollOption(id=rename.id, text="C-new"),
                        UpdateNewsPollOption(text="D-new"),
                    ],
                ),
            ]
        ),
    )
    fresh = await get_poll_by_news_id(real_db_session, news.id)
    only_q = fresh.questions[0]
    assert only_q.text == "Q1-renamed"
    texts = sorted(o.text for o in only_q.options)
    assert texts == ["A", "C-new", "D-new"]
    assert drop_id not in {o.id for o in only_q.options}


async def test_update_poll_options_locked_after_vote(real_db_session, real_editor, real_user):
    news = await _make_news(real_db_session, real_editor)
    poll = await create_poll(
        real_db_session,
        news.id,
        _simple_create_request(results_visibility="always"),
    )
    q = poll.questions[0]
    await cast_vote(
        real_db_session,
        news.id,
        real_user.id,
        [NewsPollAnswer(question_id=q.id, option_ids=[q.options[0].id])],
        NOW,
    )

    # Removing an existing option is forbidden after votes exist
    with pytest.raises(HTTPException) as exc:
        await update_poll(
            real_db_session,
            news.id,
            UpdateNewsPollRequest(
                questions=[
                    UpdateNewsPollQuestion(
                        id=q.id,
                        options=[
                            UpdateNewsPollOption(id=q.options[0].id),
                            UpdateNewsPollOption(id=q.options[1].id),
                        ],
                    )
                ]
            ),
        )
    assert exc.value.status_code == 403

    # Changing sort_order on an existing option is forbidden
    with pytest.raises(HTTPException) as exc:
        await update_poll(
            real_db_session,
            news.id,
            UpdateNewsPollRequest(
                questions=[
                    UpdateNewsPollQuestion(
                        id=q.id,
                        options=[
                            UpdateNewsPollOption(id=q.options[0].id, sort_order=9),
                            UpdateNewsPollOption(id=q.options[1].id),
                            UpdateNewsPollOption(id=q.options[2].id),
                        ],
                    )
                ]
            ),
        )
    assert exc.value.status_code == 403

    # Renaming existing option text is permitted
    await update_poll(
        real_db_session,
        news.id,
        UpdateNewsPollRequest(
            questions=[
                UpdateNewsPollQuestion(
                    id=q.id,
                    options=[
                        UpdateNewsPollOption(id=q.options[0].id, text="A-new"),
                        UpdateNewsPollOption(id=q.options[1].id),
                        UpdateNewsPollOption(id=q.options[2].id),
                    ],
                )
            ]
        ),
    )
    fresh = await get_poll_by_news_id(real_db_session, news.id)
    new_text = {o.id: o.text for o in fresh.questions[0].options}
    assert new_text[q.options[0].id] == "A-new"


async def test_update_poll_not_found(real_db_session, real_editor):
    with pytest.raises(HTTPException) as exc:
        await update_poll(
            real_db_session,
            uuid.uuid4(),
            UpdateNewsPollRequest(is_anonymous=False),
        )
    assert exc.value.status_code == 404


# ── close / reopen / delete ──────────────────────────────────────────────────


async def test_close_and_reopen_poll(real_db_session, real_editor):
    news = await _make_news(real_db_session, real_editor)
    poll = await create_poll(real_db_session, news.id, _simple_create_request())
    closed = await close_poll(real_db_session, news.id, NOW)
    assert closed.closed_at == NOW
    assert is_poll_closed(closed, NOW)

    reopened = await reopen_poll(real_db_session, news.id, NOW)
    assert reopened.closed_at is None
    _ = poll


async def test_reopen_poll_after_closes_at_rejected(real_db_session, real_editor):
    news = await _make_news(real_db_session, real_editor)
    await create_poll(
        real_db_session,
        news.id,
        _simple_create_request(closes_at=NOW - timedelta(hours=1)),
    )
    await close_poll(real_db_session, news.id, NOW)
    with pytest.raises(HTTPException) as exc:
        await reopen_poll(real_db_session, news.id, NOW)
    assert exc.value.status_code == 400


async def test_close_reopen_delete_not_found(real_db_session, real_editor):
    fake = uuid.uuid4()
    for fn in (close_poll, reopen_poll):
        with pytest.raises(HTTPException) as exc:
            await fn(real_db_session, fake, NOW)
        assert exc.value.status_code == 404

    with pytest.raises(HTTPException) as exc:
        await delete_poll(real_db_session, fake)
    assert exc.value.status_code == 404


async def test_delete_poll_cascades(real_db_session, real_editor):
    news = await _make_news(real_db_session, real_editor)
    poll = await create_poll(real_db_session, news.id, _simple_create_request())
    poll_id = poll.id

    await delete_poll(real_db_session, news.id)
    remaining = (
        await real_db_session.execute(select(NewsPoll).where(NewsPoll.id == poll_id))
    ).scalar_one_or_none()
    assert remaining is None


# ── cast_vote / revoke_vote ──────────────────────────────────────────────────


async def test_cast_vote_single_choice_and_counters(real_db_session, real_editor, real_user):
    news = await _make_news(real_db_session, real_editor)
    poll = await create_poll(
        real_db_session,
        news.id,
        _simple_create_request(results_visibility="always"),
    )
    q = poll.questions[0]
    opt = q.options[0]

    await cast_vote(
        real_db_session,
        news.id,
        real_user.id,
        [NewsPollAnswer(question_id=q.id, option_ids=[opt.id])],
        NOW,
    )
    await real_db_session.refresh(opt)
    assert opt.votes_count == 1

    voters = (await real_db_session.execute(select(NewsPollVoter))).scalars().all()
    assert len(voters) == 1


async def test_cast_vote_multi_with_custom_text(real_db_session, real_editor, real_user):
    news = await _make_news(real_db_session, real_editor)
    poll = await create_poll(
        real_db_session,
        news.id,
        _simple_create_request(
            is_multiple=True,
            allow_custom_answer=True,
            max_choices=3,
            results_visibility="always",
        ),
    )
    q = poll.questions[0]
    await cast_vote(
        real_db_session,
        news.id,
        real_user.id,
        [
            NewsPollAnswer(
                question_id=q.id,
                option_ids=[q.options[0].id, q.options[1].id],
                custom_text="hello",
            )
        ],
        NOW,
    )
    votes = (await real_db_session.execute(select(NewsPollVote))).scalars().all()
    custom = [v for v in votes if v.custom_text is not None]
    option = [v for v in votes if v.option_id is not None]
    assert len(custom) == 1 and custom[0].custom_text == "hello"
    assert len(option) == 2


async def test_cast_vote_revote_replaces_previous(real_db_session, real_editor, real_user):
    news = await _make_news(real_db_session, real_editor)
    poll = await create_poll(
        real_db_session,
        news.id,
        _simple_create_request(allow_revote=True, results_visibility="always"),
    )
    q = poll.questions[0]
    a, b = q.options[0], q.options[1]

    await cast_vote(
        real_db_session,
        news.id,
        real_user.id,
        [NewsPollAnswer(question_id=q.id, option_ids=[a.id])],
        NOW,
    )
    await cast_vote(
        real_db_session,
        news.id,
        real_user.id,
        [NewsPollAnswer(question_id=q.id, option_ids=[b.id])],
        NOW,
    )
    await real_db_session.refresh(a)
    await real_db_session.refresh(b)
    assert a.votes_count == 0
    assert b.votes_count == 1


async def test_cast_vote_revote_disallowed(real_db_session, real_editor, real_user):
    news = await _make_news(real_db_session, real_editor)
    poll = await create_poll(
        real_db_session,
        news.id,
        _simple_create_request(allow_revote=False, results_visibility="always"),
    )
    q = poll.questions[0]
    await cast_vote(
        real_db_session,
        news.id,
        real_user.id,
        [NewsPollAnswer(question_id=q.id, option_ids=[q.options[0].id])],
        NOW,
    )
    with pytest.raises(HTTPException) as exc:
        await cast_vote(
            real_db_session,
            news.id,
            real_user.id,
            [NewsPollAnswer(question_id=q.id, option_ids=[q.options[1].id])],
            NOW,
        )
    assert exc.value.status_code == 409


async def test_cast_vote_validation_errors(real_db_session, real_editor, real_user):
    news = await _make_news(real_db_session, real_editor)
    poll = await create_poll(
        real_db_session,
        news.id,
        _simple_create_request(is_multiple=True, max_choices=1, results_visibility="always"),
    )
    q = poll.questions[0]

    # max_choices exceeded
    with pytest.raises(HTTPException) as exc:
        await cast_vote(
            real_db_session,
            news.id,
            real_user.id,
            [
                NewsPollAnswer(
                    question_id=q.id,
                    option_ids=[q.options[0].id, q.options[1].id],
                )
            ],
            NOW,
        )
    assert exc.value.status_code == 409

    # option from another question
    with pytest.raises(HTTPException) as exc:
        await cast_vote(
            real_db_session,
            news.id,
            real_user.id,
            [NewsPollAnswer(question_id=q.id, option_ids=[uuid.uuid4()])],
            NOW,
        )
    assert exc.value.status_code == 422

    # unknown question
    with pytest.raises(HTTPException) as exc:
        await cast_vote(
            real_db_session,
            news.id,
            real_user.id,
            [NewsPollAnswer(question_id=uuid.uuid4(), option_ids=[q.options[0].id])],
            NOW,
        )
    assert exc.value.status_code == 422


async def test_cast_vote_required_question_missing(real_db_session, real_editor, real_user):
    news = await _make_news(real_db_session, real_editor)
    poll = await create_poll(real_db_session, news.id, _simple_create_request())
    q = poll.questions[0]
    with pytest.raises(HTTPException) as exc:
        await cast_vote(
            real_db_session,
            news.id,
            real_user.id,
            [NewsPollAnswer(question_id=q.id, option_ids=[])],
            NOW,
        )
    assert exc.value.status_code == 400


async def test_cast_vote_duplicate_option_in_one_answer(real_db_session, real_editor, real_user):
    news = await _make_news(real_db_session, real_editor)
    poll = await create_poll(
        real_db_session,
        news.id,
        _simple_create_request(is_multiple=True, results_visibility="always"),
    )
    q = poll.questions[0]
    with pytest.raises(HTTPException) as exc:
        await cast_vote(
            real_db_session,
            news.id,
            real_user.id,
            [
                NewsPollAnswer(
                    question_id=q.id,
                    option_ids=[q.options[0].id, q.options[0].id],
                )
            ],
            NOW,
        )
    assert exc.value.status_code == 400


async def test_cast_vote_custom_text_not_allowed(real_db_session, real_editor, real_user):
    news = await _make_news(real_db_session, real_editor)
    poll = await create_poll(
        real_db_session,
        news.id,
        _simple_create_request(allow_custom_answer=False, results_visibility="always"),
    )
    q = poll.questions[0]
    with pytest.raises(HTTPException) as exc:
        await cast_vote(
            real_db_session,
            news.id,
            real_user.id,
            [
                NewsPollAnswer(
                    question_id=q.id,
                    option_ids=[q.options[0].id],
                    custom_text="nope",
                )
            ],
            NOW,
        )
    assert exc.value.status_code == 400


async def test_cast_vote_after_close_rejected(real_db_session, real_editor, real_user):
    news = await _make_news(real_db_session, real_editor)
    poll = await create_poll(
        real_db_session,
        news.id,
        _simple_create_request(closes_at=NOW - timedelta(hours=1)),
    )
    with pytest.raises(HTTPException) as exc:
        await cast_vote(
            real_db_session,
            news.id,
            real_user.id,
            [
                NewsPollAnswer(
                    question_id=poll.questions[0].id, option_ids=[poll.questions[0].options[0].id]
                )
            ],
            NOW,
        )
    assert exc.value.status_code == 409


async def test_cast_vote_news_not_found(real_db_session, real_user):
    with pytest.raises(HTTPException) as exc:
        await cast_vote(
            real_db_session,
            uuid.uuid4(),
            real_user.id,
            [NewsPollAnswer(question_id=uuid.uuid4(), option_ids=[])],
            NOW,
        )
    assert exc.value.status_code == 404


async def test_revoke_vote_happy(real_db_session, real_editor, real_user):
    news = await _make_news(real_db_session, real_editor)
    poll = await create_poll(
        real_db_session,
        news.id,
        _simple_create_request(allow_revote=True, results_visibility="always"),
    )
    q = poll.questions[0]
    opt = q.options[0]

    await cast_vote(
        real_db_session,
        news.id,
        real_user.id,
        [NewsPollAnswer(question_id=q.id, option_ids=[opt.id])],
        NOW,
    )
    await revoke_vote(real_db_session, news.id, real_user.id, NOW)

    voters = (await real_db_session.execute(select(NewsPollVoter))).scalars().all()
    assert voters == []
    await real_db_session.refresh(opt)
    assert opt.votes_count == 0


async def test_revoke_vote_errors(real_db_session, real_editor, real_user):
    news = await _make_news(real_db_session, real_editor)
    # poll not found
    with pytest.raises(HTTPException) as exc:
        await revoke_vote(real_db_session, uuid.uuid4(), real_user.id, NOW)
    assert exc.value.status_code == 404

    poll = await create_poll(
        real_db_session,
        news.id,
        _simple_create_request(allow_revote=False),
    )
    # revote disallowed
    with pytest.raises(HTTPException) as exc:
        await revoke_vote(real_db_session, news.id, real_user.id, NOW)
    assert exc.value.status_code == 409

    # closed poll
    await update_poll(real_db_session, news.id, UpdateNewsPollRequest(allow_revote=True))
    await close_poll(real_db_session, news.id, NOW)
    with pytest.raises(HTTPException) as exc:
        await revoke_vote(real_db_session, news.id, real_user.id, NOW)
    assert exc.value.status_code == 409

    # user never voted
    await reopen_poll(real_db_session, news.id, NOW)
    with pytest.raises(HTTPException) as exc:
        await revoke_vote(real_db_session, news.id, real_user.id, NOW)
    assert exc.value.status_code == 404
    _ = poll


# ── get_voters_list ─────────────────────────────────────────────────────────


async def test_get_voters_list_anonymous_blocked_for_reader(
    real_db_session, real_editor, real_user
):
    news = await _make_news(real_db_session, real_editor)
    await create_poll(
        real_db_session,
        news.id,
        _simple_create_request(is_anonymous=True),
    )
    with pytest.raises(HTTPException) as exc:
        await get_voters_list(real_db_session, news.id, user=real_user, now=NOW)
    assert exc.value.status_code == 403


async def test_get_voters_list_returns_data(real_db_session, real_editor, real_user, real_admin):
    news = await _make_news(real_db_session, real_editor)
    poll = await create_poll(
        real_db_session,
        news.id,
        _simple_create_request(
            is_anonymous=False,
            is_multiple=True,
            allow_custom_answer=True,
            results_visibility="always",
        ),
    )
    q = poll.questions[0]

    await cast_vote(
        real_db_session,
        news.id,
        real_user.id,
        [
            NewsPollAnswer(
                question_id=q.id,
                option_ids=[q.options[0].id],
                custom_text="extra",
            )
        ],
        NOW,
    )

    rows = await get_voters_list(real_db_session, news.id, user=real_admin, now=NOW)
    assert len(rows) == 1
    row = rows[0]
    assert row["user"]["id"] == real_user.id
    assert row["answers"]
    answer = row["answers"][0]
    assert answer["question_id"] == q.id
    assert any(c["option_id"] == q.options[0].id for c in answer["choices"])
    assert answer["custom_text"] == "extra"


async def test_get_voters_list_poll_missing(real_db_session, real_admin):
    with pytest.raises(HTTPException) as exc:
        await get_voters_list(real_db_session, uuid.uuid4(), user=real_admin, now=NOW)
    assert exc.value.status_code == 404


# ── build_poll_public_response ───────────────────────────────────────────────


async def test_build_public_response_hides_results_until_vote(
    real_db_session, real_editor, real_user
):
    news = await _make_news(real_db_session, real_editor)
    poll = await create_poll(
        real_db_session,
        news.id,
        _simple_create_request(results_visibility="after_vote"),
    )
    poll = await get_poll_by_news_id(real_db_session, news.id)
    pub = await build_poll_public_response(real_db_session, poll, real_user, NOW)
    assert pub.can_see_results is False
    assert pub.can_vote is True
    assert pub.my_vote is None
    assert pub.total_voters is None

    q = poll.questions[0]
    await cast_vote(
        real_db_session,
        news.id,
        real_user.id,
        [NewsPollAnswer(question_id=q.id, option_ids=[q.options[0].id])],
        NOW,
    )
    poll = await get_poll_by_news_id(real_db_session, news.id)
    pub2 = await build_poll_public_response(real_db_session, poll, real_user, NOW)
    assert pub2.can_see_results is True
    assert pub2.my_vote is not None
    assert pub2.total_voters == 1
    assert pub2.can_vote is False  # allow_revote default False


async def test_build_public_response_anonymous_strips_voter(
    real_db_session, real_editor, real_user
):
    news = await _make_news(real_db_session, real_editor)
    poll = await create_poll(
        real_db_session,
        news.id,
        _simple_create_request(
            is_anonymous=True,
            is_multiple=True,
            allow_custom_answer=True,
            results_visibility="always",
        ),
    )
    q = poll.questions[0]
    await cast_vote(
        real_db_session,
        news.id,
        real_user.id,
        [
            NewsPollAnswer(
                question_id=q.id,
                option_ids=[q.options[0].id],
                custom_text="anon-text",
            )
        ],
        NOW,
    )
    poll = await get_poll_by_news_id(real_db_session, news.id)
    pub = await build_poll_public_response(real_db_session, poll, real_user, NOW)
    custom = pub.questions[0].custom_answers or []
    assert any(c.text == "anon-text" for c in custom)
    for c in custom:
        assert c.voter_id is None
        assert c.voter_name is None


async def test_build_public_response_closed_poll(real_db_session, real_editor):
    news = await _make_news(real_db_session, real_editor)
    poll = await create_poll(
        real_db_session,
        news.id,
        _simple_create_request(
            results_visibility="after_close",
            closes_at=NOW - timedelta(hours=1),
        ),
    )
    poll = await get_poll_by_news_id(real_db_session, news.id)
    pub = await build_poll_public_response(real_db_session, poll, None, NOW)
    assert pub.is_closed is True
    assert pub.can_vote is False
    assert pub.can_see_results is True


# ── get_poll_by_news_id ──────────────────────────────────────────────────────


async def test_get_poll_by_news_id_returns_none_for_missing(real_db_session):
    assert await get_poll_by_news_id(real_db_session, uuid.uuid4()) is None
