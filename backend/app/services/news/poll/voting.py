"""Vote casting and revocation."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.news import (
    NewsPoll,
    NewsPollOption,
    NewsPollQuestion,
    NewsPollVote,
    NewsPollVoter,
)
from app.schemas.news_poll import NewsPollAnswer

from ._helpers import _bad, is_poll_closed
from .queries import get_poll_by_news_id


async def _acquire_vote_lock(db: AsyncSession, poll_id: uuid.UUID, user_id: uuid.UUID) -> None:
    dialect = db.bind.dialect.name if db.bind is not None else ""
    if dialect != "postgresql":
        return
    key = f"{poll_id}:{user_id}"
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:k, 0))"),
        {"k": key},
    )


def _validate_option_ids(q: NewsPollQuestion, option_ids: list[uuid.UUID]) -> None:
    """Reject options not belonging to the question and duplicate option IDs."""
    valid_options = {o.id for o in q.options}
    for oid in option_ids:
        if oid not in valid_options:
            raise HTTPException(
                status_code=422,
                detail=f"Option {oid} does not belong to question {q.id}",
            )
    if len(set(option_ids)) != len(option_ids):
        raise _bad("Duplicate option IDs are not allowed")


def _validate_pick_count(q: NewsPollQuestion, total_picks: int) -> None:
    """Enforce single-choice exactness and the multiple-choice max_choices cap."""
    if not q.is_multiple:
        if total_picks != 1:
            raise _bad(f"Question {q.id} is single-choice and requires exactly one answer")
    elif q.max_choices is not None and total_picks > q.max_choices:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Question {q.id}: selected answers exceed the maximum"
                f" limit of {q.max_choices}"
            ),
        )


def _validate_answer(q: NewsPollQuestion, ans: NewsPollAnswer) -> None:
    """Validate a single answer against its question's constraints."""
    has_options = bool(ans.option_ids)
    has_custom = ans.custom_text is not None and ans.custom_text.strip() != ""

    if not has_options and not has_custom:
        if q.is_required:
            raise _bad(f"Question {q.id} is required")
        return

    if has_custom and not q.allow_custom_answer:
        raise _bad(f"Question {q.id} does not allow free-form answers")

    if has_options:
        _validate_option_ids(q, ans.option_ids)

    total_picks = len(ans.option_ids) + (1 if has_custom else 0)
    _validate_pick_count(q, total_picks)


def _validate_answers(poll: NewsPoll, answers: list[NewsPollAnswer]) -> None:
    questions_by_id: dict[uuid.UUID, NewsPollQuestion] = {q.id: q for q in poll.questions}
    seen: set[uuid.UUID] = set()
    for ans in answers:
        if ans.question_id in seen:
            raise _bad(f"Duplicate answer for question {ans.question_id}")
        seen.add(ans.question_id)
        q = questions_by_id.get(ans.question_id)
        if q is None:
            raise HTTPException(
                status_code=422,
                detail=f"Question {ans.question_id} does not belong to this poll",
            )
        _validate_answer(q, ans)

    answered = {a.question_id for a in answers}
    for q in poll.questions:
        if q.is_required and q.id not in answered:
            raise _bad(f"Required question {q.id} is missing in the answer set")


async def _recompute_option_counts(db: AsyncSession, poll_id: uuid.UUID) -> None:
    """Recompute votes_count for all options in this poll from votes table."""
    counts = (
        await db.execute(
            select(NewsPollVote.option_id, func.count(NewsPollVote.id))
            .where(
                NewsPollVote.poll_id == poll_id,
                NewsPollVote.option_id.isnot(None),
            )
            .group_by(NewsPollVote.option_id)
        )
    ).all()
    counts_by_id = {oid: cnt for oid, cnt in counts}

    options = (
        (
            await db.execute(
                select(NewsPollOption)
                .join(NewsPollQuestion, NewsPollOption.question_id == NewsPollQuestion.id)
                .where(NewsPollQuestion.poll_id == poll_id)
            )
        )
        .scalars()
        .all()
    )
    for opt in options:
        opt.votes_count = counts_by_id.get(opt.id, 0)


async def cast_vote(
    db: AsyncSession,
    news_id: uuid.UUID,
    user_id: uuid.UUID,
    answers: list[NewsPollAnswer],
    now: datetime,
) -> None:
    poll = await get_poll_by_news_id(db, news_id)
    if not poll:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Poll not found")

    if is_poll_closed(poll, now):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Voting is closed")

    _validate_answers(poll, answers)

    await _acquire_vote_lock(db, poll.id, user_id)

    existing_voter = (
        await db.execute(
            select(NewsPollVoter).where(
                NewsPollVoter.poll_id == poll.id, NewsPollVoter.user_id == user_id
            )
        )
    ).scalar_one_or_none()

    if existing_voter is not None:
        if not poll.allow_revote:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Already voted and revote is not allowed",
            )
        await db.execute(delete(NewsPollVote).where(NewsPollVote.voter_id == existing_voter.id))
        voter = existing_voter
    else:
        voter = NewsPollVoter(poll_id=poll.id, user_id=user_id, created_at=now)
        db.add(voter)
        await db.flush()

    for ans in answers:
        if not ans.option_ids and not (ans.custom_text and ans.custom_text.strip()):
            continue
        for opt_id in ans.option_ids:
            db.add(
                NewsPollVote(
                    poll_id=poll.id,
                    voter_id=voter.id,
                    question_id=ans.question_id,
                    option_id=opt_id,
                    created_at=now,
                )
            )
        if ans.custom_text and ans.custom_text.strip():
            db.add(
                NewsPollVote(
                    poll_id=poll.id,
                    voter_id=voter.id,
                    question_id=ans.question_id,
                    option_id=None,
                    custom_text=ans.custom_text.strip(),
                    created_at=now,
                )
            )

    await db.flush()
    await _recompute_option_counts(db, poll.id)
    await db.commit()


async def revoke_vote(
    db: AsyncSession,
    news_id: uuid.UUID,
    user_id: uuid.UUID,
    now: datetime,
) -> None:
    poll = await get_poll_by_news_id(db, news_id)
    if not poll:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Poll not found")

    if is_poll_closed(poll, now):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Voting is closed")

    if not poll.allow_revote:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Revoting/revoking is not allowed for this poll",
        )

    await _acquire_vote_lock(db, poll.id, user_id)

    voter = (
        await db.execute(
            select(NewsPollVoter).where(
                NewsPollVoter.poll_id == poll.id, NewsPollVoter.user_id == user_id
            )
        )
    ).scalar_one_or_none()
    if not voter:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="You haven't voted in this poll",
        )

    await db.delete(voter)
    await db.flush()
    await _recompute_option_counts(db, poll.id)
    await db.commit()
