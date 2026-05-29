"""Service tests."""

from datetime import datetime, timezone

import pytest

from src.bot.keyboards.builder import get_list_view_keyboard
from src.db.models import (
    ListMember,
    Medication,
    Note,
    Reminder,
    ReminderStatus,
    RepeatRule,
    User,
)
from src.services.list_service import ListService
from src.services.note_service import NoteService
from src.services.reminder_service import ReminderService


@pytest.mark.asyncio
async def test_note_service_enforces_ownership_and_archiving(db_session):
    """Users should only see and modify their own active notes."""
    user = User(telegram_id=9901, timezone="UTC")
    other = User(telegram_id=9902, timezone="UTC")
    db_session.add_all([user, other])
    await db_session.flush()

    service = NoteService(db_session)
    note = await service.create_note(user.id, "Recipe", "Step 1\nStep 2")
    other_note = await service.create_note(other.id, "Other", "Hidden")
    await db_session.flush()

    notes, total = await service.list_notes(user.id)
    assert total == 1
    assert [item.id for item in notes] == [note.id]
    assert await service.get_note(other_note.id, user.id) is None

    title_matches, title_total = await service.list_notes(user.id, search_query="rec")
    assert title_total == 1
    assert [item.id for item in title_matches] == [note.id]

    text_matches, text_total = await service.list_notes(user.id, search_query="step 2")
    assert text_total == 1
    assert [item.id for item in text_matches] == [note.id]

    hidden_matches, hidden_total = await service.list_notes(user.id, search_query="hidden")
    assert hidden_matches == []
    assert hidden_total == 0

    updated = await service.update_note(note.id, user.id, title="Updated", text="New text")
    assert updated is not None
    assert updated.title == "Updated"
    assert updated.text == "New text"

    assert await service.archive_note(note.id, other.id) is False
    assert await service.archive_note(note.id, user.id) is True
    notes, total = await service.list_notes(user.id)
    assert notes == []
    assert total == 0


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
    assert first_button.callback_data == "checklist_start_item:10:1"

    manage_keyboard = get_list_view_keyboard(10, [Item()], manage_items=True)
    manage_button = manage_keyboard.inline_keyboard[0][0]

    assert manage_button.text == "✏️ A very long list item title..."
    assert manage_button.callback_data == "list_item:1"

    checked_keyboard = get_list_view_keyboard(10, [Item()], checked_source_item_ids={1})
    checked_button = checked_keyboard.inline_keyboard[0][0]

    assert checked_button.text == "✅ A very long list item title..."
    assert checked_button.callback_data == "checklist_start_item:10:1"


@pytest.mark.asyncio
async def test_reminder_service_links_only_accessible_lists(db_session):
    """Linked list reminders should allow shared lists but keep access boundaries."""
    user = User(telegram_id=4001, timezone="UTC")
    other_user = User(telegram_id=4002, timezone="UTC")
    shared_owner = User(telegram_id=4003, timezone="UTC")
    db_session.add_all([user, other_user, shared_owner])
    await db_session.flush()

    list_service = ListService(db_session)
    reminder_service = ReminderService(db_session)
    own_list = await list_service.create_list(user.id, "Groceries")
    other_list = await list_service.create_list(other_user.id, "Hidden")
    shared_list = await list_service.create_list(shared_owner.id, "Shared errands")
    db_session.add(ListMember(list_id=shared_list.id, user_id=user.id, role="viewer"))
    await db_session.flush()
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
    shared = await reminder_service.create_reminder(
        user_id=user.id,
        text="Напомнить про общий список",
        remind_at_utc=remind_at,
        list_id=shared_list.id,
    )

    assert reminder is not None
    assert reminder.list_id == own_list.id
    assert shared is not None
    assert shared.list_id == shared_list.id
    assert blocked is None


@pytest.mark.asyncio
async def test_reminder_service_updates_keep_ownership(db_session):
    """Reminder edit operations should be scoped to the owner."""
    user = User(telegram_id=4011, timezone="UTC")
    other_user = User(telegram_id=4012, timezone="UTC")
    db_session.add_all([user, other_user])
    await db_session.flush()

    service = ReminderService(db_session)
    reminder = await service.create_reminder(
        user_id=user.id,
        text="Old reminder",
        remind_at_utc=datetime(2026, 5, 23, 10, 0, tzinfo=timezone.utc),
        repeat_rule=RepeatRule.NONE,
    )

    blocked_text = await service.update_reminder_text(reminder.id, other_user.id, "Other")
    blocked_time = await service.update_reminder_time(
        reminder.id,
        other_user.id,
        datetime(2026, 5, 24, 12, 0, tzinfo=timezone.utc),
    )
    updated_text = await service.update_reminder_text(reminder.id, user.id, "Updated")
    updated_time = await service.update_reminder_time(
        reminder.id,
        user.id,
        datetime(2026, 5, 24, 12, 0, tzinfo=timezone.utc),
    )
    updated_repeat = await service.update_reminder_repeat(reminder.id, user.id, RepeatRule.DAILY)

    assert blocked_text is None
    assert blocked_time is None
    assert updated_text.text == "Updated"
    assert updated_time.remind_at_utc.replace(tzinfo=timezone.utc) == datetime(
        2026, 5, 24, 12, 0, tzinfo=timezone.utc
    )
    assert updated_repeat.repeat_rule == RepeatRule.DAILY


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
async def test_shared_list_copy_token_is_owner_only(db_session):
    """Viewers and editors must not create tokens that re-export someone else's list."""
    owner = User(telegram_id=8051, timezone="UTC")
    editor = User(telegram_id=8052, timezone="UTC")
    viewer = User(telegram_id=8053, timezone="UTC")
    db_session.add_all([owner, editor, viewer])
    await db_session.flush()

    service = ListService(db_session)
    shared = await service.create_list(owner.id, "Private shared list")
    db_session.add_all(
        [
            ListMember(list_id=shared.id, user_id=editor.id, role="editor"),
            ListMember(list_id=shared.id, user_id=viewer.id, role="viewer"),
        ]
    )
    await db_session.flush()

    owner_token = await service.create_share_token(shared.id, owner.id)
    editor_token = await service.create_share_token(shared.id, editor.id)
    viewer_token = await service.create_share_token(shared.id, viewer.id)

    assert owner_token is not None
    assert editor_token is None
    assert viewer_token is None


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


@pytest.mark.asyncio
async def test_settings_stats_cover_visible_domains(db_session):
    """User statistics should include visible domains only."""
    from src.services.settings_service import SettingsService

    owner = User(telegram_id=8201, timezone="UTC")
    member = User(telegram_id=8202, timezone="UTC")
    db_session.add_all([owner, member])
    await db_session.flush()

    list_service = ListService(db_session)
    from src.services.driver_service import DriverService

    driver_service = DriverService(db_session)
    owned = await list_service.create_list(owner.id, "Owned")
    shared = await list_service.create_list(member.id, "Shared")
    vehicle = await driver_service.create_vehicle(owner.id, "Stats car", current_mileage_km=1000)
    await driver_service.add_fuel_entry(owner.id, vehicle.id, 1000, 40, 2400, True)
    await driver_service.add_fuel_entry(owner.id, vehicle.id, 1500, 35, 2100, True)
    db_session.add(ListMember(list_id=shared.id, user_id=owner.id, role="viewer"))
    db_session.add_all(
        [
            Medication(user_id=owner.id, name="Active med", is_active=True),
            Medication(user_id=owner.id, name="Archived med", is_active=False),
            Note(user_id=owner.id, title="Recipe", text="Flour and water", is_archived=False),
            Note(user_id=owner.id, title="Old note", text="Archive", is_archived=True),
            Reminder(
                user_id=owner.id,
                text="Active reminder",
                remind_at_utc=datetime(2026, 5, 24, 8, 0, tzinfo=timezone.utc),
                status=ReminderStatus.ACTIVE,
            ),
            Reminder(
                user_id=owner.id,
                text="Done reminder",
                remind_at_utc=datetime(2026, 5, 24, 9, 0, tzinfo=timezone.utc),
                status=ReminderStatus.DONE,
            ),
        ]
    )
    await db_session.flush()

    stats = await SettingsService(db_session).get_stats(owner.id)

    assert owned.id is not None
    assert stats["lists"] == {"owned": 1, "shared": 1}
    assert stats["notes"] == {"active": 1, "archived": 1}
    assert stats["medications"] == {"active": 1, "archived": 1}
    assert stats["checklists"] == {"active": 0, "completed": 0, "canceled": 0}
    assert stats["reminders"]["active"] == 1
    assert stats["reminders"]["done"] == 1
    assert stats["driver"]["vehicles_count"] == 1
    assert stats["driver"]["fuel_entries_count"] == 2
    assert stats["driver"]["fuel_total_cost"] == pytest.approx(4500)
    assert stats["driver"]["avg_consumption"] == pytest.approx(7.0)
