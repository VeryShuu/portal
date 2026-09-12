"""Unit-тесты чистой логики тестов и попыток (инкремент 3, ТЗ §6.3):
валидация вариантов, снапшот порядка, лимиты попыток, склейка вида попытки,
ключ участника (обе категории)."""

from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException

from app.models.learning import (
    LearningQuestion,
    LearningQuestionOption,
    LearningTest,
)
from app.schemas.learning import LearnerQuestionOut
from app.services.learning import courses_service as cs
from app.services.learning import tests_service as ts
from app.services.learning.participant import LearningParticipant


def _mk_test(**kwargs) -> LearningTest:
    defaults = dict(
        item_id=uuid.uuid4(),
        pass_score=70,
        max_attempts=3,
        shuffle_questions=False,
        shuffle_answers=False,
    )
    defaults.update(kwargs)
    return LearningTest(**defaults)


def _mk_question(multi: bool = False) -> LearningQuestion:
    # Вне БД server_default не срабатывает — id задаём явно
    return LearningQuestion(id=uuid.uuid4(), test_item_id=uuid.uuid4(), text="Вопрос?", multi=multi)


def _opt(text: str = "Вариант") -> LearningQuestionOption:
    return LearningQuestionOption(
        id=uuid.uuid4(), question_id=uuid.uuid4(), text=text, is_correct=False
    )


class TestNormalizeOptions:
    def test_assigns_sequential_sort_order(self):
        opts = [{"text": "a", "is_correct": False}, {"text": "b", "is_correct": True}]
        ts.normalize_options(opts, multi=True)
        assert [o["sort_order"] for o in opts] == [0, 1]

    def test_requires_at_least_one_correct(self):
        with pytest.raises(HTTPException) as e:
            ts.normalize_options([{"text": "a", "is_correct": False}] * 2, multi=True)
        assert e.value.status_code == 422

    def test_single_choice_forbids_multiple_correct(self):
        opts = [{"text": "a", "is_correct": True}, {"text": "b", "is_correct": True}]
        with pytest.raises(HTTPException) as e:
            ts.normalize_options(opts, multi=False)
        assert e.value.status_code == 422

    def test_multi_allows_multiple_correct(self):
        opts = [{"text": "a", "is_correct": True}, {"text": "b", "is_correct": True}]
        ts.normalize_options(opts, multi=True)
        assert all(o["is_correct"] for o in opts)


class TestRemainingAttempts:
    def test_zero_means_unlimited(self):
        assert ts.remaining_attempts(0, submitted_count=10**6) is None

    def test_counts_down(self):
        assert ts.remaining_attempts(3, 1) == 2
        assert ts.remaining_attempts(3, 5) == 0
        assert ts.remaining_attempts(1, 0) == 1


class TestSnapshotFor:
    def _pairs(self):
        q1, q2 = _mk_question(), _mk_question()
        o11, o12 = _opt(), _opt()
        o21, o22 = _opt(), _opt()
        return [(q1, [o11, o12]), (q2, [o21, o22])], {
            q1.id: [o11.id, o12.id],
            q2.id: [o21.id, o22.id],
        }

    def test_no_shuffle_preserves_order(self):
        pairs, ids = self._pairs()
        snap = ts._snapshot_for(_mk_test(), pairs)
        assert snap["version"] == 1
        assert snap["order"] == [str(qid) for qid in ids]
        assert set(snap["option_order"]) == {str(q) for q in ids}

    def test_shuffle_keeps_same_ids(self):
        pairs, _ = self._pairs()
        shuffled_test = _mk_test(shuffle_questions=True, shuffle_answers=True)
        snap_plain = ts._snapshot_for(_mk_test(), pairs)
        snap_shuffled = ts._snapshot_for(shuffled_test, pairs)
        # Те же идентификаторы, порядок может отличаться; состав не теряется.
        assert set(snap_shuffled["order"]) == set(snap_plain["order"])
        for _raw_qid, opt_ids in snap_shuffled["option_order"].items():
            assert len(opt_ids) == len(set(opt_ids)) == 2


class TestAttemptQuestionsView:
    def test_maps_snapshot_order_without_correct_flags(self):
        q = _mk_question(multi=True)
        o1, o2 = _opt("Верный"), _opt("Неверный")
        o1.is_correct = True
        snapshot = {
            "order": [str(q.id)],
            "option_order": {str(q.id): [str(o2.id), str(o1.id)]},
        }
        out = ts.attempt_questions_view(snapshot, [(q, [o1, o2])])
        assert isinstance(out[0], LearnerQuestionOut)
        assert out[0].multi is True
        # порядок — из снапшота, не из sort_order
        assert [str(o.id) for o in out[0].options] == [str(o2.id), str(o1.id)]

    def test_deleted_question_and_options_drop_out(self):
        q = _mk_question()
        o1 = _opt()
        ghost_qid = uuid.uuid4()
        ghost_oid = uuid.uuid4()
        snapshot = {
            "order": [str(q.id), str(ghost_qid)],
            "option_order": {str(q.id): [str(ghost_oid), str(o1.id)]},
        }
        out = ts.attempt_questions_view(snapshot, [(q, [o1])])
        # призрак вопроса выброшен; у живого остались только существующие варианты
        assert len(out) == 1
        assert [str(o.id) for o in out[0].options] == [str(o1.id)]


class TestLearningParticipant:
    def test_keys_match_courses_service_convention(self):
        uid, aid = uuid.uuid4(), uuid.uuid4()

        user = LearningParticipant.from_user(
            type("U", (), {"id": uid, "full_name": "Штатный Сотрудник", "email": "s@x"})()
        )
        account = LearningParticipant.from_account(
            type("A", (), {"id": aid, "full_name": "Внешний", "email": "e@x"})()
        )
        kind_u, id_u = user.key()
        kind_a, id_a = account.key()
        assert (kind_u, id_u) == ("user", uid)
        assert cs._participant_key(user_id=uid, learning_account_id=None)[0] == kind_u
        assert (kind_a, id_a) == ("acc", aid)

    def test_key_without_principal_raises(self):
        broken = LearningParticipant(kind="user")
        with pytest.raises(ValueError):
            broken.key()
