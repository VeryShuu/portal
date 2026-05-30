"""Create / update / delete / open-close operations for news polls."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.news import (
    News,
    NewsPoll,
    NewsPollOption,
    NewsPollQuestion,
    NewsPollVoter,
)
from app.schemas.news_poll import (
    CreateNewsPollQuestion,
    CreateNewsPollRequest,
    UpdateNewsPollQuestion,
    UpdateNewsPollRequest,
)

from ._helpers import (
    POLL_ALWAYS_EDITABLE,
    POLL_FROZEN_AFTER_VOTE,
    QUESTION_ALWAYS_EDITABLE,
    QUESTION_FROZEN_AFTER_VOTE,
    _aware,
    _bad,
    _forbid,
)
from .queries import get_poll_by_news_id


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
