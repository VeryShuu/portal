from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator, model_validator

ALLOWED_VISIBILITY = {"always", "after_vote", "after_close", "only_admin_editor"}


# ── Public (read) schemas ─────────────────────────────────────────────────────


class NewsPollOptionPublic(BaseModel):
    id: uuid.UUID
    text: str | None = None
    image_url: str | None = None
    sort_order: int
    votes_count: int | None = None
    votes_percent: float | None = None

    model_config = {"from_attributes": True}


class PollCustomAnswerPublic(BaseModel):
    """Aggregated free-form ("Other") answer for a question."""

    text: str
    voter_id: uuid.UUID | None = None  # None when poll is anonymous
    voter_name: str | None = None

    model_config = {"from_attributes": True}


class PollMyAnswer(BaseModel):
    """Authenticated user's submitted answer for a single question."""

    question_id: uuid.UUID
    option_ids: list[uuid.UUID] = Field(default_factory=list)
    custom_text: str | None = None


class PollMyVote(BaseModel):
    answers: list[PollMyAnswer]
    voted_at: datetime


class NewsPollQuestionPublic(BaseModel):
    id: uuid.UUID
    text: str
    sort_order: int
    is_required: bool
    is_multiple: bool
    max_choices: int | None = None
    allow_custom_answer: bool
    options: list[NewsPollOptionPublic]
    custom_answers: list[PollCustomAnswerPublic] | None = None
    total_answers: int | None = None

    model_config = {"from_attributes": True}


class NewsPollPublic(BaseModel):
    id: uuid.UUID
    news_id: uuid.UUID
    is_anonymous: bool
    allow_revote: bool
    results_visibility: str
    closes_at: datetime | None = None
    closed_at: datetime | None = None
    is_closed: bool
    total_voters: int | None = None
    questions: list[NewsPollQuestionPublic]
    my_vote: PollMyVote | None = None
    can_vote: bool
    can_see_results: bool

    model_config = {"from_attributes": True}


# ── Create / Update schemas ───────────────────────────────────────────────────


class CreateNewsPollOption(BaseModel):
    text: str | None = None
    image_url: str | None = None
    sort_order: int = 0

    @model_validator(mode="after")
    def validate_text_or_image(self) -> CreateNewsPollOption:
        if not self.text and not self.image_url:
            raise ValueError("text or image_url must be provided")
        return self


class CreateNewsPollQuestion(BaseModel):
    text: str = Field(..., min_length=1, max_length=500)
    sort_order: int = 0
    is_required: bool = True
    is_multiple: bool = False
    max_choices: int | None = None
    allow_custom_answer: bool = False
    options: list[CreateNewsPollOption]

    @model_validator(mode="after")
    def validate_question(self) -> CreateNewsPollQuestion:
        if self.max_choices is not None:
            if not self.is_multiple:
                raise ValueError("max_choices can only be specified when is_multiple is True")
            if self.max_choices < 1:
                raise ValueError("max_choices must be >= 1")

        if len(self.options) < 2 or len(self.options) > 20:
            raise ValueError("A question must have between 2 and 20 options")

        texts = [o.text.strip().lower() for o in self.options if o.text is not None]
        if len(texts) != len(set(texts)):
            raise ValueError("Duplicate option texts are not allowed within one question")
        return self


class CreateNewsPollRequest(BaseModel):
    is_anonymous: bool = True
    allow_revote: bool = False
    results_visibility: str = "after_vote"
    closes_at: datetime | None = None
    questions: list[CreateNewsPollQuestion]

    @field_validator("results_visibility")
    @classmethod
    def validate_visibility(cls, v: str) -> str:
        if v not in ALLOWED_VISIBILITY:
            raise ValueError(f"results_visibility must be one of {ALLOWED_VISIBILITY}")
        return v

    @model_validator(mode="after")
    def validate_questions(self) -> CreateNewsPollRequest:
        if not self.questions:
            raise ValueError("Poll must contain at least one question")
        if len(self.questions) > 30:
            raise ValueError("Poll cannot contain more than 30 questions")
        return self


class UpdateNewsPollOption(BaseModel):
    id: uuid.UUID | None = None
    text: str | None = None
    image_url: str | None = None
    sort_order: int | None = None


class UpdateNewsPollQuestion(BaseModel):
    id: uuid.UUID | None = None
    text: str | None = Field(None, min_length=1, max_length=500)
    sort_order: int | None = None
    is_required: bool | None = None
    is_multiple: bool | None = None
    max_choices: int | None = None
    allow_custom_answer: bool | None = None
    options: list[UpdateNewsPollOption] | None = None


class UpdateNewsPollRequest(BaseModel):
    is_anonymous: bool | None = None
    allow_revote: bool | None = None
    results_visibility: str | None = None
    closes_at: datetime | None = None
    questions: list[UpdateNewsPollQuestion] | None = None

    @field_validator("results_visibility")
    @classmethod
    def validate_visibility(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if v not in ALLOWED_VISIBILITY:
            raise ValueError(f"results_visibility must be one of {ALLOWED_VISIBILITY}")
        return v


# ── Vote request ──────────────────────────────────────────────────────────────


class NewsPollAnswer(BaseModel):
    question_id: uuid.UUID
    option_ids: list[uuid.UUID] = Field(default_factory=list)
    custom_text: str | None = Field(None, max_length=500)


class NewsPollVoteRequest(BaseModel):
    answers: list[NewsPollAnswer] = Field(..., min_length=1)
