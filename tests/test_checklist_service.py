"""Tests for personal checklist runs."""

from datetime import datetime, timedelta, timezone

import pytest

from src.db.models import ListMember, User
from src.services.checklist_service import ChecklistService
from src.services.list_service import ListService


@pytest.mark.asyncio
async def test_checklist_run_uses_snapshot_without_mutating_source_list(db_session):
    """A checklist run should not toggle the source list item completion flags."""
    user = User(telegram_id=9101, timezone="UTC")
    db_session.add(user)
    await db_session.flush()

    list_service = ListService(db_session)
    checklist_service = ChecklistService(db_session)
    todo_list = await list_service.create_list(user.id, "Перед поездкой")
    first = await list_service.add_item(todo_list.id, user.id, "Проверить масло")
    second = await list_service.add_item(todo_list.id, user.id, "Взять документы")

    run = await checklist_service.create_run_from_list(todo_list.id, user.id)
    assert run is not None
    assert run.title_snapshot == "Перед поездкой"
    assert [item.text_snapshot for item in run.items] == ["Проверить масло", "Взять документы"]

    run = await checklist_service.toggle_item(run.id, run.items[0].id, user.id)
    assert checklist_service.progress(run) == (1, 2)

    source_first = await list_service.get_item_by_id(first.id, user.id)
    source_second = await list_service.get_item_by_id(second.id, user.id)
    assert source_first.is_completed is False
    assert source_second.is_completed is False


@pytest.mark.asyncio
async def test_checklist_run_can_start_with_source_item_checked(db_session):
    """Opening a list item should create a checklist run with only that snapshot item checked."""
    user = User(telegram_id=9107, timezone="UTC")
    db_session.add(user)
    await db_session.flush()

    list_service = ListService(db_session)
    checklist_service = ChecklistService(db_session)
    todo_list = await list_service.create_list(user.id, "Проверка")
    first = await list_service.add_item(todo_list.id, user.id, "Первый пункт")
    second = await list_service.add_item(todo_list.id, user.id, "Второй пункт")

    run = await checklist_service.create_run_from_list(
        todo_list.id,
        user.id,
        initial_source_item_id=first.id,
    )

    assert run is not None
    checked_by_source = {item.source_item_id: item.checked for item in run.items}
    assert checked_by_source == {first.id: True, second.id: False}

    source_first = await list_service.get_item_by_id(first.id, user.id)
    assert source_first.is_completed is False
    assert await checklist_service.create_run_from_list(
        todo_list.id,
        user.id,
        initial_source_item_id=999999,
    ) is None


@pytest.mark.asyncio
async def test_checklist_run_finish_requires_all_items_checked(db_session):
    """A checklist run can only be completed after every snapshot item is checked."""
    user = User(telegram_id=9102, timezone="UTC")
    db_session.add(user)
    await db_session.flush()

    list_service = ListService(db_session)
    checklist_service = ChecklistService(db_session)
    todo_list = await list_service.create_list(user.id, "Покупки")
    await list_service.add_item(todo_list.id, user.id, "Молоко")
    await list_service.add_item(todo_list.id, user.id, "Хлеб")

    run = await checklist_service.create_run_from_list(todo_list.id, user.id)

    assert await checklist_service.finish_run(run.id, user.id) is None

    run = await checklist_service.check_all(run.id, user.id)
    finished = await checklist_service.finish_run(run.id, user.id)

    assert finished is not None
    assert finished.status == "completed"
    assert finished.completed_at is not None


@pytest.mark.asyncio
async def test_checklist_run_respects_shared_list_access(db_session):
    """Viewers may run a personal checklist, while outsiders cannot."""
    owner = User(telegram_id=9103, timezone="UTC")
    viewer = User(telegram_id=9104, timezone="UTC")
    outsider = User(telegram_id=9105, timezone="UTC")
    db_session.add_all([owner, viewer, outsider])
    await db_session.flush()

    list_service = ListService(db_session)
    checklist_service = ChecklistService(db_session)
    shared = await list_service.create_list(owner.id, "Общий список")
    await list_service.add_item(shared.id, owner.id, "Пункт")
    db_session.add(ListMember(list_id=shared.id, user_id=viewer.id, role="viewer"))
    await db_session.flush()

    viewer_run = await checklist_service.create_run_from_list(shared.id, viewer.id)
    outsider_run = await checklist_service.create_run_from_list(shared.id, outsider.id)

    assert viewer_run is not None
    assert viewer_run.user_id == viewer.id
    assert outsider_run is None
    assert await list_service.add_item(shared.id, viewer.id, "Нельзя") is None


@pytest.mark.asyncio
async def test_checklist_run_detects_source_list_changes(db_session):
    """The run should know when the source list changed after snapshot creation."""
    user = User(telegram_id=9106, timezone="UTC")
    db_session.add(user)
    await db_session.flush()

    list_service = ListService(db_session)
    checklist_service = ChecklistService(db_session)
    todo_list = await list_service.create_list(user.id, "Дом")
    await list_service.add_item(todo_list.id, user.id, "Полить цветы")
    run = await checklist_service.create_run_from_list(todo_list.id, user.id)

    todo_list.updated_at = datetime.now(timezone.utc) + timedelta(minutes=5)
    await db_session.flush()

    assert await checklist_service.source_changed(run) is True
