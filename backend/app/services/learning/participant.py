"""Типизированный принципал участника курса (ТЗ §7).

``CurrentLearningParticipant`` допускает обоих: сотрудника портала (портальная
сессия) и внешнюю учётку (learner-cookie). Строка вида ``("user", uuid)`` /
``("acc", uuid)`` — тот же ключ, которым курсы_service собирает прогресс
(``_participant_key``), поэтому условия запросов строятся единообразно.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from sqlalchemy import ColumnElement

if TYPE_CHECKING:
    from app.models.learning import LearningAccount
    from app.models.user import User

# Префиксы ключа участника: "user" — сотрудник портала, "acc" — внешняя учётка.
KIND_USER = "user"
KIND_ACCOUNT = "acc"


@dataclass(frozen=True, slots=True)
class LearningParticipant:
    kind: str  # KIND_USER | KIND_ACCOUNT
    user_id: uuid.UUID | None = None
    learning_account_id: uuid.UUID | None = None
    display_name: str = ""
    email: str = ""

    @classmethod
    def from_user(cls, user: User) -> LearningParticipant:
        return cls(
            kind=KIND_USER,
            user_id=user.id,
            learning_account_id=None,
            display_name=user.full_name,
            email=user.email,
        )

    @classmethod
    def from_account(cls, account: LearningAccount) -> LearningParticipant:
        return cls(
            kind=KIND_ACCOUNT,
            user_id=None,
            learning_account_id=account.id,
            display_name=account.full_name,
            email=account.email,
        )

    def key(self) -> tuple[str, uuid.UUID]:
        """Совместимо с courses_service._participant_key («user» / «acc»)."""
        ident = self.user_id if self.kind == KIND_USER else self.learning_account_id
        if ident is None:
            raise ValueError(f"participant without principal id (kind={self.kind})")
        return self.kind, ident

    def matching(self, model: Any) -> ColumnElement[bool]:
        """SQL-условие «строка принадлежит этому участнику» для XOR-колонок."""
        if self.kind == KIND_USER:
            return cast(ColumnElement[bool], model.user_id == self.user_id)
        return cast(ColumnElement[bool], model.learning_account_id == self.learning_account_id)


__all__ = ["KIND_ACCOUNT", "KIND_USER", "LearningParticipant"]
