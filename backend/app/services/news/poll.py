"""News poll service: multi-question polls with optional questions and free-form answers."""

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.news import (
    News,
    NewsPoll,
    NewsPollOption,
    NewsPollQuestion,
    NewsPollVote,
    NewsPollVoter,
)
from app.models.user import User
from app.schemas.news_poll import (
    CreateNewsPollQuestion,
    CreateNewsPollRequest,
    NewsPollAnswer,
    NewsPollOptionPublic,
    NewsPollPublic,
    NewsPollQuestionPublic,
    PollCustomAnswerPublic,
    PollMyAnswer,
    PollMyVote,
    UpdateNewsPollQuestion,
    UpdateNewsPollRequest,
)

PRIVILEGED_ROLES = ("editor", "admin")

POLL_ALWAYS_EDITABLE = ("closes_at",)
POLL_FROZEN_AFTER_VOTE = ("is_anonymous", "allow_revote", "results_visibility")

QUESTION_ALWAYS_EDITABLE = ("text", "sort_order")
QUESTION_FROZEN_AFTER_VOTE = (
    "is_required",
    "is_multiple",
    "max_choices",
    "allow_custom_answer",
)


def _is_privileged(user: User | None) -> bool:
    return user is not None and user.role in PRIVILEGED_ROLES


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def _forbid(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


def _bad(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


def is_poll_closed(poll: NewsPoll, now: datetime) -> bool:
    if poll.closed_at is not None:
        return True
    return poll.closes_at is not None and _aware(poll.closes_at) <= now


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


def _can_see_results(poll: NewsPoll, user: User | None, has_voted: bool, is_closed: bool) -> bool:
    if _is_privileged(user):
        return True
    if poll.results_visibility == "only_admin_editor":
        return False
    if poll.results_visibility == "always":
        return True
    if poll.results_visibility == "after_vote":
        return has_voted
    if poll.results_visibility == "after_close":
        return is_closed
    return False


# ── Build public response ────────────────────────────────────────────────────


async def build_poll_public_response(
    db: AsyncSession,
    poll: NewsPoll,
    user: User | None,
    now: datetime,
) -> NewsPollPublic:
    is_closed = is_poll_closed(poll, now)

    # Load this user's votes (if any) along with the voter timestamp
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

    # Per-question total answers (distinct voters who answered the question)
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

    # Custom answers per question (only if results visible)
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


# ── Create / Update ──────────────────────────────────────────────────────────


def _build_question(q: CreateNewsPollQuestion, default_sort: int) -> NewsPollQuestion:
    question = NewsPollQuestion(
        text=q.text,
        sort_order=q.sort_order if q.sort_order != 0 else default_sort,
        is_required=q.is_required,
        is_multiple=q.is_multiple,
        max_choices=q.max_choices,
        allow_custom_answer=q.allow_custom_answer,
    )
    for i, opt in enumerate(q.options):
        question.options.append(
            NewsPollOption(
                text=opt.text,
                image_url=opt.image_url,
                sort_order=opt.sort_order if opt.sort_order != 0 else i,
            )
        )
    return question


async def create_poll(
    db: AsyncSession,
    news_id: uuid.UUID,
    data: CreateNewsPollRequest,
) -> NewsPoll:
    news = (await db.execute(select(News).where(News.id == news_id))).scalar_one_or_none()
    if not news:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="News not found")

    existing = (
        await db.execute(select(NewsPoll.id).where(NewsPoll.news_id == news_id))
    ).scalar_one_or_none()
    if existing:
        raise _bad("News article already has a poll")

    poll = NewsPoll(
        news_id=news_id,
        is_anonymous=data.is_anonymous,
        allow_revote=data.allow_revote,
        results_visibility=data.results_visibility,
        closes_at=data.closes_at,
    )
    for i, q in enumerate(data.questions):
        poll.questions.append(_build_question(q, default_sort=i))

    db.add(poll)
    await db.commit()
    await db.refresh(poll)
    return poll


def _apply_poll_settings(
    poll: NewsPoll, data: UpdateNewsPollRequest, *, restricted: bool
) -> None:
    provided = data.model_dump(exclude_unset=True)
    if restricted:
        for field in POLL_FROZEN_AFTER_VOTE:
            if field in provided and provided[field] != getattr(poll, field):
                raise _forbid(f"Cannot change {field} after voting has started")
        for field in POLL_ALWAYS_EDITABLE:
            if field in provided:
                setattr(poll, field, provided[field])
    else:
        for field in (*POLL_ALWAYS_EDITABLE, *POLL_FROZEN_AFTER_VOTE):
            if field in provided:
                setattr(poll, field, provided[field])


def _apply_question_settings(
    q: NewsPollQuestion, inp: UpdateNewsPollQuestion, *, restricted: bool
) -> None:
    provided = inp.model_dump(exclude_unset=True, exclude={"id", "options"})
    if restricted:
        for field in QUESTION_FROZEN_AFTER_VOTE:
            if field in provided and provided[field] != getattr(q, field):
                raise _forbid(f"Cannot change question.{field} after voting has started")
        for field in QUESTION_ALWAYS_EDITABLE:
            if field in provided:
                setattr(q, field, provided[field])
    else:
        for field in (*QUESTION_ALWAYS_EDITABLE, *QUESTION_FROZEN_AFTER_VOTE):
            if field in provided:
                setattr(q, field, provided[field])
        if q.max_choices is not None:
            if not q.is_multiple:
                raise _bad("max_choices can only be specified when is_multiple is True")
            if q.max_choices < 1:
                raise _bad("max_choices must be >= 1")


def _apply_options_locked(
    q: NewsPollQuestion, inp_options: list | None
) -> None:
    if inp_options is None:
        return
    input_by_id = {o.id: o for o in inp_options if o.id is not None}
    if len(input_by_id) != len(q.options):
        raise _forbid("Cannot add or remove options after voting has started")
    for db_opt in q.options:
        i = input_by_id.get(db_opt.id)
        if i is None:
            raise _forbid("All existing options must be provided with their IDs")
        if i.sort_order is not None and i.sort_order != db_opt.sort_order:
            raise _forbid("Cannot change option sort order after voting has started")
        if i.image_url is not None and i.image_url != db_opt.image_url:
            raise _forbid("Cannot change option image after voting has started")
        if i.text is not None:
            db_opt.text = i.text


async def _apply_options_unlocked(
    db: AsyncSession, q: NewsPollQuestion, inp_options: list | None
) -> None:
    if inp_options is None:
        return
    if len(inp_options) < 2 or len(inp_options) > 20:
        raise _bad("A question must have between 2 and 20 options")

    texts = [o.text.strip().lower() for o in inp_options if o.text is not None]
    if len(texts) != len(set(texts)):
        raise _bad("Duplicate option texts are not allowed within one question")

    existing_by_id = {o.id: o for o in q.options}
    incoming_ids = {o.id for o in inp_options if o.id is not None}

    for opt_id, db_opt in list(existing_by_id.items()):
        if opt_id not in incoming_ids:
            await db.delete(db_opt)
            existing_by_id.pop(opt_id, None)

    for i, inp in enumerate(inp_options):
        target_sort = inp.sort_order if inp.sort_order is not None else i
        provided = inp.model_fields_set
        if inp.id is not None and inp.id in existing_by_id:
            db_opt = existing_by_id[inp.id]
            if "text" in provided:
                db_opt.text = inp.text
            if "image_url" in provided:
                db_opt.image_url = inp.image_url
            db_opt.sort_order = target_sort
            if not db_opt.text and not db_opt.image_url:
                raise _bad("Each option must have either text or image_url")
        else:
            if not inp.text and not inp.image_url:
                raise _bad("Each option must have either text or image_url")
            q.options.append(
                NewsPollOption(
                    text=inp.text,
                    image_url=inp.image_url,
                    sort_order=target_sort,
                )
            )


async def _apply_questions(
    db: AsyncSession,
    poll: NewsPoll,
    inp_questions: list[UpdateNewsPollQuestion] | None,
    *,
    restricted: bool,
) -> None:
    if inp_questions is None:
        return

    existing_by_id = {q.id: q for q in poll.questions}
    incoming_ids = {q.id for q in inp_questions if q.id is not None}

    if restricted:
        if incoming_ids != set(existing_by_id.keys()) or len(inp_questions) != len(poll.questions):
            raise _forbid("Cannot add or remove questions after voting has started")
        for inp in inp_questions:
            db_q = existing_by_id[inp.id]  # type: ignore[index]
            _apply_question_settings(db_q, inp, restricted=True)
            _apply_options_locked(db_q, inp.options)
        return

    if not inp_questions:
        raise _bad("Poll must contain at least one question")
    if len(inp_questions) > 30:
        raise _bad("Poll cannot contain more than 30 questions")

    # Remove deleted
    for qid, db_q in list(existing_by_id.items()):
        if qid not in incoming_ids:
            await db.delete(db_q)
            existing_by_id.pop(qid, None)

    for i, inp in enumerate(inp_questions):
        target_sort = inp.sort_order if inp.sort_order is not None else i
        if inp.id is not None and inp.id in existing_by_id:
            db_q = existing_by_id[inp.id]
            _apply_question_settings(db_q, inp, restricted=False)
            db_q.sort_order = target_sort
            await _apply_options_unlocked(db, db_q, inp.options)
        else:
            if not inp.text or not inp.options:
                raise _bad("New questions require text and options")
            new_q = NewsPollQuestion(
                text=inp.text,
                sort_order=target_sort,
                is_required=inp.is_required if inp.is_required is not None else True,
                is_multiple=inp.is_multiple if inp.is_multiple is not None else False,
                max_choices=inp.max_choices,
                allow_custom_answer=inp.allow_custom_answer
                if inp.allow_custom_answer is not None
                else False,
            )
            poll.questions.append(new_q)
            await db.flush()
            await _apply_options_unlocked(db, new_q, inp.options)


async def update_poll(
    db: AsyncSession,
    news_id: uuid.UUID,
    data: UpdateNewsPollRequest,
) -> NewsPoll:
    poll = await get_poll_by_news_id(db, news_id)
    if not poll:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Poll not found")

    votes_exist = (
        await db.execute(
            select(func.count(NewsPollVoter.id)).where(NewsPollVoter.poll_id == poll.id)
        )
    ).scalar_one() > 0

    _apply_poll_settings(poll, data, restricted=votes_exist)
    await _apply_questions(db, poll, data.questions, restricted=votes_exist)

    poll.updated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(poll)
    return poll


async def delete_poll(db: AsyncSession, news_id: uuid.UUID) -> None:
    poll = await get_poll_by_news_id(db, news_id)
    if not poll:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Poll not found")
    await db.delete(poll)
    await db.commit()


async def close_poll(db: AsyncSession, news_id: uuid.UUID, now: datetime) -> NewsPoll:
    poll = await get_poll_by_news_id(db, news_id)
    if not poll:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Poll not found")
    poll.closed_at = now
    poll.updated_at = now
    await db.commit()
    await db.refresh(poll)
    return poll


async def reopen_poll(db: AsyncSession, news_id: uuid.UUID, now: datetime) -> NewsPoll:
    poll = await get_poll_by_news_id(db, news_id)
    if not poll:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Poll not found")
    if poll.closes_at is not None and _aware(poll.closes_at) <= now:
        raise _bad("Cannot reopen the poll because closes_at has already passed")
    poll.closed_at = None
    poll.updated_at = now
    await db.commit()
    await db.refresh(poll)
    return poll


# ── Voting ───────────────────────────────────────────────────────────────────


async def _acquire_vote_lock(db: AsyncSession, poll_id: uuid.UUID, user_id: uuid.UUID) -> None:
    dialect = db.bind.dialect.name if db.bind is not None else ""
    if dialect != "postgresql":
        return
    key = f"{poll_id}:{user_id}"
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:k, 0))"),
        {"k": key},
    )


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
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Question {ans.question_id} does not belong to this poll",
            )

        has_options = bool(ans.option_ids)
        has_custom = ans.custom_text is not None and ans.custom_text.strip() != ""

        if not has_options and not has_custom:
            # Empty answer is allowed only for optional questions
            if q.is_required:
                raise _bad(f"Question {q.id} is required")
            continue

        if has_custom and not q.allow_custom_answer:
            raise _bad(f"Question {q.id} does not allow free-form answers")

        if has_options:
            valid_options = {o.id for o in q.options}
            for oid in ans.option_ids:
                if oid not in valid_options:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail=f"Option {oid} does not belong to question {q.id}",
                    )
            if len(set(ans.option_ids)) != len(ans.option_ids):
                raise _bad("Duplicate option IDs are not allowed")

        total_picks = len(ans.option_ids) + (1 if has_custom else 0)
        if not q.is_multiple:
            if total_picks != 1:
                raise _bad(
                    f"Question {q.id} is single-choice and requires exactly one answer"
                )
        else:
            if q.max_choices is not None and total_picks > q.max_choices:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        f"Question {q.id}: selected answers exceed the maximum"
                        f" limit of {q.max_choices}"
                    ),
                )

    # Ensure all required questions are present
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
        await db.execute(
            select(NewsPollOption)
            .join(NewsPollQuestion, NewsPollOption.question_id == NewsPollQuestion.id)
            .where(NewsPollQuestion.poll_id == poll_id)
        )
    ).scalars().all()
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
        await db.execute(
            delete(NewsPollVote).where(NewsPollVote.voter_id == existing_voter.id)
        )
        voter = existing_voter
    else:
        voter = NewsPollVoter(poll_id=poll.id, user_id=user_id, created_at=now)
        db.add(voter)
        await db.flush()

    for ans in answers:
        # Skip purely empty answers for optional questions
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


# ── Voters listing ───────────────────────────────────────────────────────────


async def get_voters_list(
    db: AsyncSession,
    news_id: uuid.UUID,
    *,
    user: User,
    now: datetime,  # noqa: ARG001 — kept for parity with caller
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
        # Group votes per question
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
