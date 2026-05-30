"""Read-only queries: fetch poll, build public response, list voters."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.news import (
    NewsPoll,
    NewsPollOption,
    NewsPollQuestion,
    NewsPollVote,
    NewsPollVoter,
)
from app.models.user import User
from app.schemas.news_poll import (
    NewsPollOptionPublic,
    NewsPollPublic,
    NewsPollQuestionPublic,
    PollCustomAnswerPublic,
    PollMyAnswer,
    PollMyVote,
)

from ._helpers import _can_see_results, _is_privileged, is_poll_closed


async def get_poll_by_news_id(db: AsyncSession, news_id: uuid.UUID) -> NewsPoll | None:
    stmt = (
        select(NewsPoll)
        .where(NewsPoll.news_id == news_id)
        .options(
            selectinload(NewsPoll.questions).selectinload(NewsPollQuestion.options),
            selectinload(NewsPoll.news),
        )
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def build_poll_public_response(
    db: AsyncSession,
    poll: NewsPoll,
    user: User | None,
    now: datetime,
) -> NewsPollPublic:
    is_closed = is_poll_closed(poll, now)

    my_vote: PollMyVote | None = None
    if user is not None:
        voter_stmt = (
            select(NewsPollVoter)
            .where(NewsPollVoter.poll_id == poll.id, NewsPollVoter.user_id == user.id)
            .options(selectinload(NewsPollVoter.votes))
        )
        voter = (await db.execute(voter_stmt)).scalar_one_or_none()
        if voter:
            by_question: dict[uuid.UUID, PollMyAnswer] = {}
            for v in voter.votes:
                ans = by_question.setdefault(
                    v.question_id,
                    PollMyAnswer(question_id=v.question_id, option_ids=[], custom_text=None),
                )
                if v.option_id is not None:
                    ans.option_ids.append(v.option_id)
                if v.custom_text is not None:
                    ans.custom_text = v.custom_text
            my_vote = PollMyVote(
                answers=list(by_question.values()),
                voted_at=voter.created_at,
            )

    has_voted = my_vote is not None
    can_vote = user is not None and not is_closed and (not has_voted or poll.allow_revote)
    can_see_results = _can_see_results(poll, user, has_voted=has_voted, is_closed=is_closed)

    total_voters = (
        await db.execute(
            select(func.count(NewsPollVoter.id)).where(NewsPollVoter.poll_id == poll.id)
        )
    ).scalar_one()

    question_totals: dict[uuid.UUID, int] = {}
    if can_see_results:
        rows = await db.execute(
            select(
                NewsPollVote.question_id,
                func.count(func.distinct(NewsPollVote.voter_id)),
            )
            .where(NewsPollVote.poll_id == poll.id)
            .group_by(NewsPollVote.question_id)
        )
        question_totals = {qid: cnt for qid, cnt in rows.all()}

    custom_by_question: dict[uuid.UUID, list[PollCustomAnswerPublic]] = {}
    if can_see_results:
        stmt = (
            select(NewsPollVote, NewsPollVoter)
            .join(NewsPollVoter, NewsPollVote.voter_id == NewsPollVoter.id)
            .where(
                NewsPollVote.poll_id == poll.id,
                NewsPollVote.custom_text.isnot(None),
            )
            .options(selectinload(NewsPollVoter.user))
        )
        rows2 = (await db.execute(stmt)).all()
        for vote, voter in rows2:
            entry = PollCustomAnswerPublic(
                text=vote.custom_text or "",
                voter_id=None if poll.is_anonymous and not _is_privileged(user) else voter.user_id,
                voter_name=(
                    None
                    if poll.is_anonymous and not _is_privileged(user)
                    else (voter.user.full_name if voter.user else None)
                ),
            )
            custom_by_question.setdefault(vote.question_id, []).append(entry)

    questions_public: list[NewsPollQuestionPublic] = []
    for q in sorted(poll.questions, key=lambda q: q.sort_order):
        q_total = question_totals.get(q.id, 0)
        options_public: list[NewsPollOptionPublic] = []
        for opt in sorted(q.options, key=lambda o: o.sort_order):
            votes_count = None
            votes_percent = None
            if can_see_results:
                votes_count = opt.votes_count
                votes_percent = (
                    round((opt.votes_count / q_total) * 100.0, 1) if q_total > 0 else 0.0
                )
            options_public.append(
                NewsPollOptionPublic(
                    id=opt.id,
                    text=opt.text,
                    image_url=opt.image_url,
                    sort_order=opt.sort_order,
                    votes_count=votes_count,
                    votes_percent=votes_percent,
                )
            )
        questions_public.append(
            NewsPollQuestionPublic(
                id=q.id,
                text=q.text,
                sort_order=q.sort_order,
                is_required=q.is_required,
                is_multiple=q.is_multiple,
                max_choices=q.max_choices,
                allow_custom_answer=q.allow_custom_answer,
                options=options_public,
                custom_answers=custom_by_question.get(q.id, []) if can_see_results else None,
                total_answers=q_total if can_see_results else None,
            )
        )

    return NewsPollPublic(
        id=poll.id,
        news_id=poll.news_id,
        is_anonymous=poll.is_anonymous,
        allow_revote=poll.allow_revote,
        results_visibility=poll.results_visibility,
        closes_at=poll.closes_at,
        closed_at=poll.closed_at,
        is_closed=is_closed,
        total_voters=total_voters if can_see_results else None,
        questions=questions_public,
        my_vote=my_vote,
        can_vote=can_vote,
        can_see_results=can_see_results,
    )


async def get_voters_list(
    db: AsyncSession,
    news_id: uuid.UUID,
    *,
    user: User,
    now: datetime,
) -> list[dict[str, Any]]:
    poll = await get_poll_by_news_id(db, news_id)
    if not poll:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Poll not found")

    privileged = _is_privileged(user)
    if poll.is_anonymous and not privileged:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This poll is anonymous. Only editors/admins can view voters.",
        )

    voters = (
        await db.execute(
            select(NewsPollVoter)
            .where(NewsPollVoter.poll_id == poll.id)
            .options(
                selectinload(NewsPollVoter.votes),
                selectinload(NewsPollVoter.user),
            )
        )
    ).scalars().all()

    options_by_id: dict[uuid.UUID, NewsPollOption] = {}
    questions_by_id: dict[uuid.UUID, NewsPollQuestion] = {}
    for q in poll.questions:
        questions_by_id[q.id] = q
        for o in q.options:
            options_by_id[o.id] = o

    result: list[dict[str, Any]] = []
    for voter in voters:
        u = voter.user
        if not u:
            continue
        per_q: dict[uuid.UUID, dict[str, Any]] = {}
        for v in voter.votes:
            entry = per_q.setdefault(
                v.question_id,
                {
                    "question_id": v.question_id,
                    "question_text": questions_by_id[v.question_id].text
                    if v.question_id in questions_by_id
                    else None,
                    "choices": [],
                    "custom_text": None,
                },
            )
            if v.option_id is not None:
                entry["choices"].append(
                    {
                        "option_id": v.option_id,
                        "text": options_by_id[v.option_id].text
                        if v.option_id in options_by_id
                        else None,
                    }
                )
            elif v.custom_text is not None:
                entry["custom_text"] = v.custom_text
        result.append(
            {
                "user": {
                    "id": u.id,
                    "full_name": u.full_name,
                    "email": u.email,
                },
                "voted_at": voter.created_at,
                "answers": list(per_q.values()),
            }
        )

    return result
