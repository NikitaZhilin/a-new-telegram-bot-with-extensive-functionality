"""Service tests."""

from datetime import datetime, timezone

import pytest

from src.bot.keyboards.builder import get_list_view_keyboard
from src.db.models import RepeatRule, User
from src.services.list_service import ListService
from src.services.reminder_service import ReminderService

@pytest.mark.asyncio
async def test_list_service_item_ownership(db_session):
    """Users must not manage items from other users' lists."""
    user = User(telegram_id=1001, timezone="UTC")
    other_user = User(telegram_id=1002, timezone="UTC")
    db_session.add_all([user, other_user])
    await db_session.flush()

    service = ListService(db_session)
    list_obj = await service.create_list(user.id, "Groceries")
    other_list = await service.create_list(other_user.id, "Other")
    item = await service.add_item(list_obj.id, user.id, "Milk")
    other_item = await service.add_item(other_list.id, other_user.id, "Tea")

    assert await service.toggle_item_by_id(other_item.id, user.id) is None
    assert await service.delete_item_by_id(other_item.id, user.id) is False

    toggled = await service.toggle_item_by_id(item.id, user.id)
    assert toggled is not None
    assert toggled.is_completed is True

    deleted = await service.delete_item_by_id(item.id, user.id)
    assert deleted is True
    assert await service.get_item_by_id(item.id, user.id) is None


@pytest.mark.asyncio
async def test_list_service_paginates_user_lists(db_session):
    """List pagination should be scoped to the owner."""
    user = User(telegram_id=2001, timezone="UTC")
    other_user = User(telegram_id=2002, timezone="UTC")
    db_session.add_all([user, other_user])
    await db_session.flush()

    service = ListService(db_session)
    for index in range(3):
        await service.create_list(user.id, f"List {index}")
    await service.create_list(other_user.id, "Hidden")

    first_page, total = await service.get_lists_list(user.id, page=0, page_size=2)
    second_page, second_total = await service.get_lists_list(user.id, page=1, page_size=2)

    assert total == 3
    assert second_total == 3
    assert len(first_page) == 2
    assert len(second_page) == 1


@pytest.mark.asyncio
async def test_list_service_formats_share_text_and_keeps_ownership(db_session):
    """Share text should be plain and scoped to the owner."""
    user = User(telegram_id=3001, timezone="UTC")
    other_user = User(telegram_id=3002, timezone="UTC")
    db_session.add_all([user, other_user])
    await db_session.flush()

    service = ListService(db_session)
    list_obj = await service.create_list(user.id, "Weekend")
    first_item = await service.add_item(list_obj.id, user.id, "Buy milk")
    await service.add_item(list_obj.id, user.id, "Call mom")
    await service.toggle_item_by_id(first_item.id, user.id)

    text = await service.format_list_as_text(list_obj.id, user.id)
    other_text = await service.format_list_as_text(list_obj.id, other_user.id)

    assert other_text is None
    assert text == "📋 Weekend\n\n1. ✅ Buy milk\n2. ⬜ Call mom"


def test_list_keyboard_truncates_long_item_buttons():
    """Long item labels should not stretch Telegram inline buttons."""
    class Item:
        id = 1
        is_completed = False
        text = "A very long list item title that should not stretch the button"

    keyboard = get_list_view_keyboard(10, [Item()])
    first_button = keyboard.inline_keyboard[0][0]

    assert first_button.text == "⬜ A very long list item title..."
    assert first_button.callback_data == "list_item:1"


@pytest.mark.asyncio
async def test_reminder_service_links_only_owned_lists(db_session):
    """Linked list reminders should keep ownership boundaries."""
    user = User(telegram_id=4001, timezone="UTC")
    other_user = User(telegram_id=4002, timezone="UTC")
    db_session.add_all([user, other_user])
    await db_session.flush()

    list_service = ListService(db_session)
    reminder_service = ReminderService(db_session)
    own_list = await list_service.create_list(user.id, "Groceries")
    other_list = await list_service.create_list(other_user.id, "Hidden")
    remind_at = datetime(2026, 5, 23, 10, 0, tzinfo=timezone.utc)

    reminder = await reminder_service.create_reminder(
        user_id=user.id,
        text="Напомнить про список: Groceries",
        remind_at_utc=remind_at,
        repeat_rule=RepeatRule.NONE,
        list_id=own_list.id,
    )
    blocked = await reminder_service.create_reminder(
        user_id=user.id,
        text="Bad link",
        remind_at_utc=remind_at,
        list_id=other_list.id,
    )

    assert reminder is not None
    assert reminder.list_id == own_list.id
    assert blocked is None


@pytest.mark.asyncio
async def test_list_share_token_imports_copy_for_another_user(db_session):
    """Sharing should copy a list without granting access to the original."""
    owner = User(telegram_id=7001, timezone="UTC")
    recipient = User(telegram_id=7002, timezone="UTC")
    db_session.add_all([owner, recipient])
    await db_session.flush()

    service = ListService(db_session)
    source = await service.create_list(owner.id, "Shared groceries")
    item = await service.add_item(source.id, owner.id, "Milk")
    await service.toggle_item_by_id(item.id, owner.id)
    share = await service.create_share_token(source.id, owner.id)

    copied = await service.import_shared_list(share.token, recipient.id)

    assert copied is not None
    assert copied.user_id == recipient.id
    assert copied.title == "Shared groceries (копия)"
    assert await service.get_list(source.id, recipient.id) is None
    copied_items = await service.get_list_items(copied.id, recipient.id)
    assert [(item.text, item.is_completed) for item in copied_items] == [("Milk", True)]


@pytest.mark.asyncio
async def test_list_share_token_rejects_ownerless_or_invalid_token(db_session):
    """Invalid share tokens should not import data."""
    recipient = User(telegram_id=7003, timezone="UTC")
    db_session.add(recipient)
    await db_session.flush()

    service = ListService(db_session)

    assert await service.import_shared_list("missing", recipient.id) is None


@pytest.mark.asyncio
async def test_shared_list_roles_control_access(db_session):
    """Shared list members should see the same list with role-based write access."""
    owner = User(telegram_id=8001, timezone="UTC")
    editor = User(telegram_id=8002, timezone="UTC")
    viewer = User(telegram_id=8003, timezone="UTC")
    outsider = User(telegram_id=8004, timezone="UTC")
    db_session.add_all([owner, editor, viewer, outsider])
    await db_session.flush()

    service = ListService(db_session)
    shared = await service.create_list(owner.id, "Family groceries")
    item = await service.add_item(shared.id, owner.id, "Milk")
    editor_token = await service.create_collaboration_token(shared.id, owner.id, role="editor")
    viewer_token = await service.create_collaboration_token(shared.id, owner.id, role="viewer")

    editor_list = await service.join_shared_list(editor_token.token, editor.id)
    viewer_list = await service.join_shared_list(viewer_token.token, viewer.id)

    assert editor_list.id == shared.id
    assert viewer_list.id == shared.id
    assert await service.get_access_role(shared.id, owner.id) == "owner"
    assert await service.get_access_role(shared.id, editor.id) == "editor"
    assert await service.get_access_role(shared.id, viewer.id) == "viewer"
    assert await service.get_list(shared.id, outsider.id) is None

    lists, total = await service.get_lists_list(editor.id)
    assert total == 1
    assert lists[0].id == shared.id

    edited = await service.add_item(shared.id, editor.id, "Bread")
    toggled = await service.toggle_item_by_id(item.id, editor.id)

    assert edited is not None
    assert toggled is not None
    assert toggled.is_completed is True

    assert await service.add_item(shared.id, viewer.id, "Tea") is None
    assert await service.toggle_item_by_id(item.id, viewer.id) is None
    assert await service.update_list_title(shared.id, editor.id, "Nope") is None
    assert await service.delete_list(shared.id, editor.id) is False


@pytest.mark.asyncio
async def test_shared_list_owner_can_manage_members(db_session):
    """Owners should see members, change roles, and revoke access."""
    owner = User(telegram_id=8101, username="owner", timezone="UTC")
    member_user = User(telegram_id=8102, username="member", timezone="UTC")
    outsider = User(telegram_id=8103, username="outsider", timezone="UTC")
    db_session.add_all([owner, member_user, outsider])
    await db_session.flush()

    service = ListService(db_session)
    shared = await service.create_list(owner.id, "Shared")
    token = await service.create_collaboration_token(shared.id, owner.id, role="viewer")
    await service.join_shared_list(token.token, member_user.id)

    members = await service.get_list_members(shared.id, owner.id)

    assert [member["role"] for member in members] == ["owner", "viewer"]
    assert members[0]["display_name"] == "@owner"
    member_id = members[1]["member_id"]

    assert await service.get_list_members(shared.id, outsider.id) is None
    assert await service.update_member_role(shared.id, outsider.id, member_id, "editor") is None

    updated = await service.update_member_role(shared.id, owner.id, member_id, "editor")

    assert updated is not None
    assert await service.get_access_role(shared.id, member_user.id) == "editor"
    assert await service.remove_member(shared.id, outsider.id, member_id) is False
    assert await service.remove_member(shared.id, owner.id, member_id) is True
    assert await service.get_access_role(shared.id, member_user.id) is None
