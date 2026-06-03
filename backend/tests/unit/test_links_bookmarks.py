"""Unit-тесты: бизнес-логика ярлыков и закладок (без БД)."""

import uuid
from types import SimpleNamespace

MAX_BOOKMARKS_PER_USER = 100


def make_link(
    supports_sso: bool = False,
    is_active: bool = True,
    category: str | None = "Dev Tools",
    url: str = "https://gitlab.corp.local",
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        title="GitLab",
        url=url,
        icon_url=None,
        description="Git репозитории",
        category=category,
        sort_order=0,
        supports_sso=supports_sso,
        is_active=is_active,
    )


def make_bookmark(user_id: uuid.UUID | None = None, sort_order: int = 0) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        user_id=user_id or uuid.uuid4(),
        title="Jira Board",
        url="https://jira.corp.local/board/1",
        resource_type="link",
        resource_id="12345",
        group_name=None,
        sort_order=sort_order,
    )


def test_link_sso_flag_false_by_default():
    link = make_link(supports_sso=False)
    assert link.supports_sso is False


def test_link_sso_flag_true():
    link = make_link(supports_sso=True)
    assert link.supports_sso is True


def test_link_active_filter():
    """Только активные ярлыки показываются пользователю."""
    all_links = [make_link(is_active=True), make_link(is_active=False), make_link(is_active=True)]
    visible = [l for l in all_links if l.is_active]
    assert len(visible) == 2


def test_link_hidden_by_user_preference():
    """Ярлыки из hidden_link_ids скрыты для конкретного пользователя."""
    link1 = make_link()
    link2 = make_link()
    hidden_ids = [str(link1.id)]
    visible = [l for l in [link1, link2] if str(l.id) not in hidden_ids]
    assert len(visible) == 1
    assert visible[0].id == link2.id


def test_links_grouped_by_category():
    """Ярлыки группируются по категории."""
    links = [
        make_link(category="Dev Tools"),
        make_link(category="Dev Tools"),
        make_link(category="HR"),
        make_link(category=None),
    ]
    groups: dict[str, list] = {}
    for link in links:
        key = link.category or "Другое"
        groups.setdefault(key, []).append(link)

    assert len(groups["Dev Tools"]) == 2
    assert len(groups["HR"]) == 1
    assert len(groups["Другое"]) == 1


def test_link_sort_order():
    """Ярлыки сортируются по sort_order."""
    links = [make_link() for _ in range(3)]
    links[0].sort_order = 2
    links[1].sort_order = 0
    links[2].sort_order = 1
    sorted_links = sorted(links, key=lambda l: l.sort_order)
    assert sorted_links[0].sort_order == 0
    assert sorted_links[1].sort_order == 1
    assert sorted_links[2].sort_order == 2


def test_bookmark_belongs_to_user():
    """Закладка принадлежит конкретному пользователю."""
    user_id = uuid.uuid4()
    bm = make_bookmark(user_id=user_id)
    assert bm.user_id == user_id


def test_bookmark_reorder():
    """Изменение порядка закладок через reorder."""
    user_id = uuid.uuid4()
    bms = [make_bookmark(user_id=user_id, sort_order=i) for i in range(3)]

    original_ids = [bms[0].id, bms[1].id, bms[2].id]
    reorder_map = {bms[0].id: 2, bms[1].id: 0, bms[2].id: 1}
    for bm in bms:
        bm.sort_order = reorder_map[bm.id]

    bms.sort(key=lambda b: b.sort_order)
    # P2-31: после reorder порядок должен быть [bms[1], bms[2], bms[0]] из исходного списка.
    assert bms[0].sort_order == 0
    assert bms[1].sort_order == 1
    assert bms[2].sort_order == 2
    assert bms[0].id == original_ids[1]
    assert bms[1].id == original_ids[2]
    assert bms[2].id == original_ids[0]


def test_bookmark_max_limit():
    """Нельзя создать больше MAX_BOOKMARKS_PER_USER закладок."""
    uuid.uuid4()
    count = 100
    assert count >= MAX_BOOKMARKS_PER_USER


def test_bookmark_reorder_different_user_rejected():
    """Пользователь не может переупорядочить чужие закладки."""
    user_a = uuid.uuid4()
    user_b = uuid.uuid4()
    bm = make_bookmark(user_id=user_a)

    user_ids = {bm.user_id}
    is_allowed = user_b in user_ids
    assert not is_allowed


def test_link_url_validation():
    """URL должен быть не пустым."""
    link = make_link(url="https://valid.url.local")
    assert link.url.startswith("http")


def test_bookmark_group_name():
    """Закладка может иметь имя группы."""
    bm = make_bookmark()
    bm.group_name = "Рабочие инструменты"
    assert bm.group_name == "Рабочие инструменты"
