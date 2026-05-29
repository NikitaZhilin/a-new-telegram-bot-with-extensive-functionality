"""
Database models for RememberMe Bot.

All datetime fields are stored in UTC (timezone-aware).
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum as SQLAlchemyEnum,
    ForeignKey,
    Float,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
    relationship,
)

from src.db.base import Base


class ReminderStatus(str, Enum):
    """Reminder status."""
    ACTIVE = "active"
    DONE = "done"
    CANCELED = "canceled"
    MISSED = "missed"


class RepeatRule(str, Enum):
    """Reminder repeat rule."""
    NONE = "none"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class MedicationIntakeStatus(str, Enum):
    """Medication intake mark status."""
    TAKEN = "taken"
    SKIPPED = "skipped"


class User(Base):
    """User model for storing Telegram user information."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    first_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    last_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    timezone: Mapped[str] = mapped_column(String(50), nullable=False, default="UTC")
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0", nullable=False, index=True)
    onboarding_source: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )

    # Relationships
    notes = relationship(
        "Note",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin"
    )
    todo_lists = relationship(
        "TodoList",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin"
    )
    reminders = relationship(
        "Reminder",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin"
    )
    medications = relationship(
        "Medication",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin"
    )
    subscriptions = relationship(
        "UserSubscription",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="UserSubscription.created_at.desc()",
    )
    driver_vehicles = relationship(
        "DriverVehicle",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="DriverVehicle.created_at.desc()",
    )
    driver_fuel_entries = relationship(
        "DriverFuelEntry",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="DriverFuelEntry.filled_at_utc.desc()",
    )
    driver_expenses = relationship(
        "DriverExpense",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="DriverExpense.spent_at_utc.desc()",
    )
    driver_documents = relationship(
        "DriverDocument",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="DriverDocument.expires_at_utc.asc().nullslast()",
    )
    driver_journal_entries = relationship(
        "DriverJournalEntry",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="DriverJournalEntry.happened_at_utc.desc()",
    )
    activity_events = relationship(
        "BotActivityEvent",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="BotActivityEvent.created_at.desc()",
    )
    web_login_tokens = relationship(
        "WebLoginToken",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="WebLoginToken.created_at.desc()",
    )
    checklist_runs = relationship(
        "ChecklistRun",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="ChecklistRun.created_at.desc()",
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, telegram_id={self.telegram_id})>"


class WebLoginToken(Base):
    """Hashed user access token for the standalone web client."""

    __tablename__ = "web_login_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    expires_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    last_used_at_utc: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    use_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    user = relationship("User", back_populates="web_login_tokens")


class Note(Base):
    """Note model for storing user notes."""

    __tablename__ = "notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(String(40), nullable=False, default="other", server_default="other", index=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )

    # Relationships
    user = relationship("User", back_populates="notes")

    def __repr__(self) -> str:
        return f"<Note(id={self.id}, user_id={self.user_id}, category='{self.category}', title='{self.title}')>"


class UserSubscription(Base):
    """Subscription state for monetized bot features."""

    __tablename__ = "user_subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    plan_code: Mapped[str] = mapped_column(String(50), nullable=False, default="free", index=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="active", index=True)
    starts_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    expires_at_utc: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    provider: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    provider_payment_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    user = relationship("User", back_populates="subscriptions")

    __table_args__ = (
        Index("ix_user_subscriptions_user_status", "user_id", "status"),
    )

    def __repr__(self) -> str:
        return f"<UserSubscription(user_id={self.user_id}, plan='{self.plan_code}', status='{self.status}')>"


class BotActivityEvent(Base):
    """Sanitized bot interaction event for admin diagnostics."""

    __tablename__ = "bot_activity_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    telegram_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, index=True)
    source: Mapped[str] = mapped_column(String(30), nullable=False, default="telegram", server_default="telegram")
    event_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    event_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    domain: Mapped[str] = mapped_column(String(30), nullable=False, default="general", server_default="general", index=True)
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    user = relationship("User", back_populates="activity_events")

    __table_args__ = (
        Index("ix_bot_activity_user_created", "user_id", "created_at"),
        Index("ix_bot_activity_domain_created", "domain", "created_at"),
        Index("ix_bot_activity_event_created", "event_name", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<BotActivityEvent(user_id={self.user_id}, event='{self.event_name}')>"


class ServiceHeartbeat(Base):
    """Runtime heartbeat written by api, bot, and worker processes."""

    __tablename__ = "service_heartbeats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    service_name: Mapped[str] = mapped_column(String(60), unique=True, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ok", server_default="ok", index=True)
    version: Mapped[str] = mapped_column(String(80), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    uptime_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint("status IN ('ok', 'degraded', 'down')", name="ck_service_heartbeats_status"),
        Index("ix_service_heartbeats_service_seen", "service_name", "last_seen_at"),
    )

    def __repr__(self) -> str:
        return f"<ServiceHeartbeat(service_name='{self.service_name}', status='{self.status}')>"


class TodoList(Base):
    """TodoList model for storing todo/shopping lists."""

    __tablename__ = "lists"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    source_module: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="general",
        server_default="general",
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )

    # Relationships
    user = relationship("User", back_populates="todo_lists")
    items = relationship(
        "ListItem",
        back_populates="todo_list",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="ListItem.position"
    )
    reminders = relationship(
        "Reminder",
        back_populates="todo_list",
        lazy="selectin"
    )
    checklist_runs = relationship(
        "ChecklistRun",
        back_populates="source_list",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<TodoList(id={self.id}, user_id={self.user_id}, title='{self.title}')>"


class ListItem(Base):
    """ListItem model for storing list items."""

    __tablename__ = "list_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    list_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("lists.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    text: Mapped[str] = mapped_column(String(500), nullable=False)
    is_completed: Mapped[bool] = mapped_column(Boolean, server_default="false", nullable=False, index=True)
    position: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

    # Relationships
    todo_list = relationship("TodoList", back_populates="items")

    def __repr__(self) -> str:
        return f"<ListItem(id={self.id}, list_id={self.list_id}, text='{self.text[:30]}...')>"


class ListShareToken(Base):
    """A token that lets another user copy a list."""

    __tablename__ = "list_share_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    list_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("lists.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_by_user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    uses_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_uses: Mapped[int] = mapped_column(Integer, nullable=False, default=20)
    token_type: Mapped[str] = mapped_column(String(20), nullable=False, default="copy", server_default="copy")
    access_role: Mapped[str] = mapped_column(String(20), nullable=False, default="editor", server_default="editor")
    expires_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="true", nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    todo_list = relationship("TodoList")
    created_by = relationship("User")

    def __repr__(self) -> str:
        return f"<ListShareToken(id={self.id}, list_id={self.list_id})>"


class ListMember(Base):
    """A user who has access to a shared list."""

    __tablename__ = "list_members"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    list_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("lists.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="viewer")
    invited_by_user_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    todo_list = relationship("TodoList")
    user = relationship("User", foreign_keys=[user_id])
    invited_by = relationship("User", foreign_keys=[invited_by_user_id])

    __table_args__ = (
        Index("ux_list_members_list_user", "list_id", "user_id", unique=True),
    )

    def __repr__(self) -> str:
        return f"<ListMember(list_id={self.list_id}, user_id={self.user_id}, role='{self.role}')>"


class ChecklistRun(Base):
    """A personal interactive checklist execution snapshot."""

    __tablename__ = "checklist_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_list_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("lists.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    driver_vehicle_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("driver_vehicles.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    title_snapshot: Mapped[str] = mapped_column(String(255), nullable=False)
    source_updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active", server_default="active", index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)

    user = relationship("User", back_populates="checklist_runs")
    source_list = relationship("TodoList", back_populates="checklist_runs")
    driver_vehicle = relationship("DriverVehicle")
    items = relationship(
        "ChecklistRunItem",
        back_populates="run",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="ChecklistRunItem.position",
    )

    __table_args__ = (
        CheckConstraint("status IN ('active', 'completed', 'canceled')", name="ck_checklist_runs_status"),
        Index("ix_checklist_runs_user_status", "user_id", "status"),
        Index("ix_checklist_runs_list_created", "source_list_id", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<ChecklistRun(id={self.id}, user_id={self.user_id}, status='{self.status}')>"


class ChecklistRunItem(Base):
    """A snapshot item inside a personal checklist run."""

    __tablename__ = "checklist_run_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("checklist_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_item_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("list_items.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    text_snapshot: Mapped[str] = mapped_column(String(500), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    checked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false", index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    run = relationship("ChecklistRun", back_populates="items")
    source_item = relationship("ListItem")

    __table_args__ = (
        Index("ix_checklist_run_items_run_position", "run_id", "position"),
    )

    def __repr__(self) -> str:
        return f"<ChecklistRunItem(id={self.id}, run_id={self.run_id}, checked={self.checked})>"


class DriverVehicle(Base):
    """Vehicle profile for the driver assistant."""

    __tablename__ = "driver_vehicles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    preset_slug: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    make: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    model: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    body_type: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    engine_volume_l: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    engine_power_hp: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    fuel_type: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    transmission: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    drive_type: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    expected_consumption_city_l_per_100: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    expected_consumption_highway_l_per_100: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    expected_consumption_mixed_l_per_100: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    vehicle_specs_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    manual_mileage_km: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    current_mileage_km: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    service_interval_km: Mapped[int] = mapped_column(Integer, nullable=False, default=10000, server_default="10000")
    service_interval_months: Mapped[int] = mapped_column(Integer, nullable=False, default=12, server_default="12")
    last_service_mileage_km: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    last_service_at_utc: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    user = relationship("User", back_populates="driver_vehicles")
    fuel_entries = relationship(
        "DriverFuelEntry",
        back_populates="vehicle",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="DriverFuelEntry.filled_at_utc.desc()",
    )
    expenses = relationship(
        "DriverExpense",
        back_populates="vehicle",
        lazy="selectin",
        order_by="DriverExpense.spent_at_utc.desc()",
    )
    documents = relationship(
        "DriverDocument",
        back_populates="vehicle",
        lazy="selectin",
        order_by="DriverDocument.expires_at_utc.asc().nullslast()",
    )
    journal_entries = relationship(
        "DriverJournalEntry",
        back_populates="vehicle",
        lazy="selectin",
        order_by="DriverJournalEntry.happened_at_utc.desc()",
    )

    __table_args__ = (
        CheckConstraint("manual_mileage_km >= 0", name="ck_driver_vehicles_manual_mileage_non_negative"),
        CheckConstraint("current_mileage_km >= 0", name="ck_driver_vehicles_current_mileage_non_negative"),
        CheckConstraint("service_interval_km > 0", name="ck_driver_vehicles_service_interval_km_positive"),
        CheckConstraint("service_interval_months > 0", name="ck_driver_vehicles_service_interval_months_positive"),
        CheckConstraint("year IS NULL OR (year >= 1886 AND year <= 2100)", name="ck_driver_vehicles_year_reasonable"),
        CheckConstraint("engine_volume_l IS NULL OR engine_volume_l > 0", name="ck_driver_vehicles_engine_volume_positive"),
        CheckConstraint("engine_power_hp IS NULL OR engine_power_hp > 0", name="ck_driver_vehicles_engine_power_positive"),
        CheckConstraint(
            "expected_consumption_city_l_per_100 IS NULL OR expected_consumption_city_l_per_100 > 0",
            name="ck_driver_vehicles_consumption_city_positive",
        ),
        CheckConstraint(
            "expected_consumption_highway_l_per_100 IS NULL OR expected_consumption_highway_l_per_100 > 0",
            name="ck_driver_vehicles_consumption_highway_positive",
        ),
        CheckConstraint(
            "expected_consumption_mixed_l_per_100 IS NULL OR expected_consumption_mixed_l_per_100 > 0",
            name="ck_driver_vehicles_consumption_mixed_positive",
        ),
        CheckConstraint(
            "last_service_mileage_km IS NULL OR last_service_mileage_km >= 0",
            name="ck_driver_vehicles_last_service_mileage_non_negative",
        ),
        Index("ix_driver_vehicles_user_created", "user_id", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<DriverVehicle(id={self.id}, user_id={self.user_id}, title='{self.title}')>"


class DriverFuelEntry(Base):
    """Fuel log entry for a vehicle."""

    __tablename__ = "driver_fuel_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    vehicle_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("driver_vehicles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    mileage_km: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    liters: Mapped[float] = mapped_column(Float, nullable=False)
    total_cost: Mapped[float] = mapped_column(Float, nullable=False)
    price_per_liter: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    is_full_tank: Mapped[bool] = mapped_column(Boolean, server_default="true", nullable=False, index=True)
    station: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    consumption_l_per_100: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    cost_per_km: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    filled_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    user = relationship("User", back_populates="driver_fuel_entries")
    vehicle = relationship("DriverVehicle", back_populates="fuel_entries")

    __table_args__ = (
        CheckConstraint("mileage_km >= 0", name="ck_driver_fuel_entries_mileage_non_negative"),
        CheckConstraint("liters > 0", name="ck_driver_fuel_entries_liters_positive"),
        CheckConstraint("total_cost > 0", name="ck_driver_fuel_entries_total_cost_positive"),
        CheckConstraint(
            "price_per_liter IS NULL OR price_per_liter > 0",
            name="ck_driver_fuel_entries_price_positive",
        ),
        CheckConstraint(
            "consumption_l_per_100 IS NULL OR consumption_l_per_100 >= 0",
            name="ck_driver_fuel_entries_consumption_non_negative",
        ),
        CheckConstraint(
            "cost_per_km IS NULL OR cost_per_km >= 0",
            name="ck_driver_fuel_entries_cost_per_km_non_negative",
        ),
        Index("ix_driver_fuel_vehicle_mileage", "vehicle_id", "mileage_km"),
        Index("ix_driver_fuel_user_filled", "user_id", "filled_at_utc"),
    )

    def __repr__(self) -> str:
        return f"<DriverFuelEntry(id={self.id}, vehicle_id={self.vehicle_id}, mileage={self.mileage_km})>"


class DriverExpense(Base):
    """Manual vehicle expense not covered by fuel journal."""

    __tablename__ = "driver_expenses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    vehicle_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("driver_vehicles.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(80), nullable=False, default="other", server_default="other")
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    spent_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    user = relationship("User", back_populates="driver_expenses")
    vehicle = relationship("DriverVehicle", back_populates="expenses")

    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_driver_expenses_amount_positive"),
        Index("ix_driver_expenses_user_spent", "user_id", "spent_at_utc"),
        Index("ix_driver_expenses_vehicle_spent", "vehicle_id", "spent_at_utc"),
    )

    def __repr__(self) -> str:
        return f"<DriverExpense(id={self.id}, user_id={self.user_id}, amount={self.amount})>"


class DriverDocument(Base):
    """Vehicle-related document or recurring payment expiry tracker."""

    __tablename__ = "driver_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    vehicle_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("driver_vehicles.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    document_type: Mapped[str] = mapped_column(String(80), nullable=False, default="other", server_default="other")
    identifier: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    expires_at_utc: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    remind_before_days: Mapped[int] = mapped_column(Integer, nullable=False, default=14, server_default="14")
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true", index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    user = relationship("User", back_populates="driver_documents")
    vehicle = relationship("DriverVehicle", back_populates="documents")
    reminders = relationship(
        "Reminder",
        back_populates="driver_document",
        lazy="selectin",
    )

    __table_args__ = (
        CheckConstraint("remind_before_days >= 0", name="ck_driver_documents_remind_non_negative"),
        Index("ix_driver_documents_user_expires", "user_id", "expires_at_utc"),
        Index("ix_driver_documents_vehicle_expires", "vehicle_id", "expires_at_utc"),
    )

    def __repr__(self) -> str:
        return f"<DriverDocument(id={self.id}, user_id={self.user_id}, title='{self.title}')>"


class DriverJournalEntry(Base):
    """Driver event journal entry."""

    __tablename__ = "driver_journal_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    vehicle_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("driver_vehicles.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    checklist_run_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("checklist_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(String(80), nullable=False, default="note", server_default="note", index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="completed", server_default="completed", index=True)
    happened_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    user = relationship("User", back_populates="driver_journal_entries")
    vehicle = relationship("DriverVehicle", back_populates="journal_entries")
    checklist_run = relationship("ChecklistRun")

    __table_args__ = (
        CheckConstraint("status IN ('completed', 'planned', 'canceled', 'note')", name="ck_driver_journal_status"),
        UniqueConstraint("checklist_run_id", name="ux_driver_journal_checklist_run"),
        Index("ix_driver_journal_user_happened", "user_id", "happened_at_utc"),
        Index("ix_driver_journal_vehicle_happened", "vehicle_id", "happened_at_utc"),
        Index("ix_driver_journal_user_type", "user_id", "event_type"),
    )

    def __repr__(self) -> str:
        return f"<DriverJournalEntry(id={self.id}, user_id={self.user_id}, type='{self.event_type}')>"


class Reminder(Base):
    """
    Reminder model for storing user reminders.

    All times are stored in UTC (timezone-aware datetime).
    """

    __tablename__ = "reminders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    list_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("lists.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )
    medication_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("medications.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )
    driver_document_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("driver_documents.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    source_module: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="general",
        server_default="general",
        index=True,
    )
    remind_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True
    )
    repeat_rule: Mapped[RepeatRule] = mapped_column(
        SQLAlchemyEnum(RepeatRule),
        default=RepeatRule.NONE,
        nullable=False
    )
    status: Mapped[ReminderStatus] = mapped_column(
        SQLAlchemyEnum(ReminderStatus),
        default=ReminderStatus.ACTIVE,
        nullable=False,
        index=True
    )
    notified_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )

    # Relationships
    user = relationship("User", back_populates="reminders")
    todo_list = relationship("TodoList", back_populates="reminders")
    medication = relationship("Medication", back_populates="reminders")
    driver_document = relationship("DriverDocument", back_populates="reminders")

    # Indexes
    __table_args__ = (
        Index("ix_reminders_user_status", "user_id", "status"),
        Index("ix_reminders_remind_at_status", "remind_at_utc", "status"),
        Index("ix_reminders_user_source_status", "user_id", "source_module", "status"),
        Index("ix_reminders_driver_document_status", "driver_document_id", "status"),
    )

    def __repr__(self) -> str:
        return f"<Reminder(id={self.id}, user_id={self.user_id}, status={self.status})>"


class Medication(Base):
    """Medication schedule tracked by a user."""

    __tablename__ = "medications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    dosage: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    instructions: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    importance: Mapped[str] = mapped_column(String(20), nullable=False, default="normal", server_default="normal")
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="true", nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    user = relationship("User", back_populates="medications")
    intakes = relationship(
        "MedicationIntake",
        back_populates="medication",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="MedicationIntake.taken_at_utc.desc()",
    )
    reminders = relationship(
        "Reminder",
        back_populates="medication",
        lazy="selectin",
    )

    __table_args__ = (
        Index("ix_medications_user_active", "user_id", "is_active"),
    )

    def __repr__(self) -> str:
        return f"<Medication(id={self.id}, user_id={self.user_id}, name='{self.name}')>"


class MedicationIntake(Base):
    """A single medication intake mark."""

    __tablename__ = "medication_intakes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    medication_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("medications.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    taken_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    scheduled_slot_at_utc: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )
    status: Mapped[MedicationIntakeStatus] = mapped_column(
        SQLAlchemyEnum(MedicationIntakeStatus),
        default=MedicationIntakeStatus.TAKEN,
        nullable=False,
        index=True,
    )
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    medication_name_snapshot: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    dosage_snapshot: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    instructions_snapshot: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    importance_snapshot: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    medication = relationship("Medication", back_populates="intakes")

    __table_args__ = (
        Index("ix_medication_intakes_user_taken", "user_id", "taken_at_utc"),
        Index("ix_medication_intakes_med_slot", "medication_id", "scheduled_slot_at_utc"),
    )

    def __repr__(self) -> str:
        return f"<MedicationIntake(id={self.id}, medication_id={self.medication_id})>"
