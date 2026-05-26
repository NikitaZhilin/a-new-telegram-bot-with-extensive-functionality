"""
Telegram bot application factory.

Creates and configures the PTB application with all handlers.
"""

import logging
from telegram import Update
from telegram.error import BadRequest
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    ContextTypes,
    TypeHandler,
)

from src.config import settings
from src.bot.handlers import (
    start_handler,
    help_handler,
    import_list_handler,
    join_list_handler,
    back_handler,
    home_handler,
    list_create_conv,
    list_add_item_conv,
    list_add_bulk_conv,
    list_edit_item_conv,
    list_rename_conv,
    medication_create_conv,
    medication_edit_conv,
    medication_reminder_conv,
    reminder_create_conv,
    reminder_edit_conv,
    driver_document_conv,
    driver_expense_conv,
    driver_fuel_create_conv,
    driver_service_conv,
    driver_vehicle_create_conv,
    driver_vehicle_mileage_conv,
    settings_timezone_conv,
)
logger = logging.getLogger(__name__)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Keep stale Telegram callback errors from breaking the visible bot flow."""
    error = context.error
    if isinstance(error, BadRequest):
        message = str(error)
        if "Query is too old" in message:
            logger.info("Ignored stale Telegram callback query")
            return
        if "Message is not modified" in message:
            logger.info("Ignored Telegram message-not-modified callback")
            return

    logger.exception("Unhandled bot update error", exc_info=error)


# Import handlers for callback registration
from src.bot.handlers.lists import (
    lists_list_callback,
    lists_page_callback,
    list_view_callback,
    list_delete_callback,
    list_delete_confirm_callback,
    list_share_callback,
    list_members_callback,
    list_member_manage_callback,
    list_member_role_callback,
    list_member_remove_callback,
    list_item_callback,
    list_item_toggle_callback,
    list_item_delete_callback,
    list_item_delete_confirm_callback,
)
from src.bot.handlers.checklists import (
    checklist_cancel_callback,
    checklist_check_all_callback,
    checklist_finish_callback,
    checklist_start_callback,
    checklist_toggle_callback,
)
from src.bot.handlers.medications import (
    medications_list_callback,
    medications_page_callback,
    medication_view_callback,
    medication_edit_callback,
    medication_edit_dosage_value_callback,
    medication_edit_importance_start_callback,
    medication_edit_importance_value_callback,
    medication_edit_instructions_value_callback,
    medication_mark_taken_callback,
    medication_skip_callback,
    medication_snooze_callback,
    medication_remind_callback,
    medication_reminder_frequency_callback,
    medication_reminder_skip_callback,
    medication_reminder_time_callback,
    medication_delete_callback,
    medication_delete_confirm_callback,
)
from src.bot.handlers.reminders import (
    reminders_list_callback,
    reminders_page_callback,
    reminder_view_callback,
    reminder_done_callback,
    reminder_cancel_callback,
    reminder_delete_callback,
    reminder_edit_repeat_start,
    reminder_edit_repeat_value_callback,
    reminders_filter_callback,
)
from src.bot.handlers.settings import (
    settings_about_callback,
    settings_menu_callback,
    settings_release_history_callback,
    settings_stats_callback,
    settings_subscription_callback,
    settings_technical_status_callback,
    settings_web_login_callback,
)
from src.bot.handlers.driver import (
    driver_document_delete_callback,
    driver_document_delete_confirm_callback,
    driver_document_view_callback,
    driver_expense_delete_callback,
    driver_expense_delete_confirm_callback,
    driver_expense_view_callback,
    driver_fuel_delete_callback,
    driver_fuel_delete_confirm_callback,
    driver_fuel_history_callback,
    driver_fuel_view_callback,
    driver_list_template_callback,
    driver_menu_callback,
    driver_section_callback,
    driver_service_view_callback,
    driver_vehicle_delete_callback,
    driver_vehicle_delete_confirm_callback,
    driver_vehicle_view_callback,
)
from src.bot.handlers.navigation import menu_button_handler
from src.bot.handlers.navigation import removed_notes_callback, share_bot_callback
from src.bot.handlers.activity import activity_event_handler


def create_application() -> Application:
    """
    Create and configure the Telegram bot application.
    
    Returns:
        Configured PTB Application
    """
    # Build application
    application = (
        ApplicationBuilder()
        .token(settings.BOT_TOKEN)
        .connection_pool_size(10)
        .read_timeout(10)
        .write_timeout(10)
        .connect_timeout(10)
        .pool_timeout(10)
        .build()
    )

    application.add_handler(
        TypeHandler(Update, activity_event_handler, block=False),
        group=-1,
    )
    
    # === Command Handlers ===
    application.add_handler(start_handler)
    application.add_handler(help_handler)
    application.add_handler(import_list_handler)
    application.add_handler(join_list_handler)
    
    # === Conversation Handlers ===
    # Lists
    application.add_handler(list_create_conv)
    application.add_handler(list_add_item_conv)
    application.add_handler(list_add_bulk_conv)
    application.add_handler(list_edit_item_conv)
    application.add_handler(list_rename_conv)

    # Medications
    application.add_handler(medication_create_conv)
    application.add_handler(medication_edit_conv)
    application.add_handler(medication_reminder_conv)
    
    # Reminders
    application.add_handler(reminder_create_conv)
    application.add_handler(reminder_edit_conv)

    # Driver
    application.add_handler(driver_vehicle_create_conv)
    application.add_handler(driver_vehicle_mileage_conv)
    application.add_handler(driver_fuel_create_conv)
    application.add_handler(driver_expense_conv)
    application.add_handler(driver_document_conv)
    application.add_handler(driver_service_conv)

    # Settings
    application.add_handler(settings_timezone_conv)
    
    # === Callback Query Handlers ===
    # Navigation
    application.add_handler(back_handler)
    application.add_handler(home_handler)
    
    # Removed notes callbacks. Old messages may still contain these buttons.
    application.add_handler(CallbackQueryHandler(removed_notes_callback, pattern="^(notes_|note_)"))
    
    # Lists callbacks
    application.add_handler(CallbackQueryHandler(lists_list_callback, pattern="^lists_list$"))
    application.add_handler(CallbackQueryHandler(list_view_callback, pattern="^list_view:"))
    application.add_handler(CallbackQueryHandler(list_delete_callback, pattern="^list_delete:"))
    application.add_handler(CallbackQueryHandler(list_delete_confirm_callback, pattern="^list_delete_confirm:"))
    application.add_handler(CallbackQueryHandler(list_share_callback, pattern="^list_share:"))
    application.add_handler(CallbackQueryHandler(list_members_callback, pattern="^list_members:"))
    application.add_handler(CallbackQueryHandler(list_member_role_callback, pattern="^list_member_role:"))
    application.add_handler(CallbackQueryHandler(list_member_remove_callback, pattern="^list_member_remove:"))
    application.add_handler(CallbackQueryHandler(list_member_manage_callback, pattern="^list_member:"))
    application.add_handler(CallbackQueryHandler(list_item_callback, pattern="^list_item:"))
    application.add_handler(CallbackQueryHandler(list_item_toggle_callback, pattern="^list_item_toggle:"))
    application.add_handler(CallbackQueryHandler(list_item_delete_callback, pattern="^list_item_delete:"))
    application.add_handler(CallbackQueryHandler(list_item_delete_confirm_callback, pattern="^list_item_delete_confirm:"))
    application.add_handler(CallbackQueryHandler(lists_page_callback, pattern="^lists_page:"))
    application.add_handler(CallbackQueryHandler(checklist_start_callback, pattern="^checklist_start:"))
    application.add_handler(CallbackQueryHandler(checklist_toggle_callback, pattern="^checklist_toggle:"))
    application.add_handler(CallbackQueryHandler(checklist_check_all_callback, pattern="^checklist_check_all:"))
    application.add_handler(CallbackQueryHandler(checklist_finish_callback, pattern="^checklist_finish:"))
    application.add_handler(CallbackQueryHandler(checklist_cancel_callback, pattern="^checklist_cancel:"))

    # Medications callbacks
    application.add_handler(CallbackQueryHandler(medications_list_callback, pattern="^medications_list$"))
    application.add_handler(CallbackQueryHandler(medications_page_callback, pattern="^med_page:"))
    application.add_handler(CallbackQueryHandler(medication_view_callback, pattern="^med_view:"))
    application.add_handler(CallbackQueryHandler(medication_edit_dosage_value_callback, pattern="^med_edit_dosage_value:"))
    application.add_handler(CallbackQueryHandler(medication_edit_instructions_value_callback, pattern="^med_edit_instr_value:"))
    application.add_handler(CallbackQueryHandler(medication_edit_importance_value_callback, pattern="^med_edit_importance_value:"))
    application.add_handler(CallbackQueryHandler(medication_edit_importance_start_callback, pattern="^med_edit_importance:"))
    application.add_handler(CallbackQueryHandler(medication_edit_callback, pattern="^med_edit:"))
    application.add_handler(CallbackQueryHandler(medication_mark_taken_callback, pattern="^med_taken:"))
    application.add_handler(CallbackQueryHandler(medication_skip_callback, pattern="^med_skip:"))
    application.add_handler(CallbackQueryHandler(medication_snooze_callback, pattern="^med_snooze:"))
    application.add_handler(CallbackQueryHandler(medication_remind_callback, pattern="^med_remind:"))
    application.add_handler(CallbackQueryHandler(medication_reminder_frequency_callback, pattern="^med_rem_freq:"))
    application.add_handler(CallbackQueryHandler(medication_reminder_time_callback, pattern="^med_rem_time:"))
    application.add_handler(CallbackQueryHandler(medication_reminder_skip_callback, pattern="^med_rem_skip:"))
    application.add_handler(CallbackQueryHandler(medication_delete_confirm_callback, pattern="^med_delete_confirm:"))
    application.add_handler(CallbackQueryHandler(medication_delete_callback, pattern="^med_delete:"))
    
    # Reminders callbacks
    application.add_handler(CallbackQueryHandler(reminders_list_callback, pattern="^reminders_list$"))
    application.add_handler(CallbackQueryHandler(reminder_view_callback, pattern="^reminder_view:"))
    application.add_handler(CallbackQueryHandler(reminder_done_callback, pattern="^reminder_done:"))
    application.add_handler(CallbackQueryHandler(reminder_cancel_callback, pattern="^reminder_cancel:"))
    application.add_handler(CallbackQueryHandler(reminder_delete_callback, pattern="^reminder_delete:"))
    application.add_handler(CallbackQueryHandler(reminder_edit_repeat_value_callback, pattern="^reminder_edit_repeat_value:"))
    application.add_handler(CallbackQueryHandler(reminder_edit_repeat_start, pattern="^reminder_edit_repeat:"))
    application.add_handler(CallbackQueryHandler(reminders_filter_callback, pattern="^reminders_filter_"))
    application.add_handler(CallbackQueryHandler(reminders_page_callback, pattern="^reminders_page:"))

    # Settings callbacks
    application.add_handler(CallbackQueryHandler(settings_menu_callback, pattern="^settings_menu$"))
    application.add_handler(CallbackQueryHandler(settings_about_callback, pattern="^settings_about$"))
    application.add_handler(CallbackQueryHandler(settings_release_history_callback, pattern="^settings_release_history$"))
    application.add_handler(CallbackQueryHandler(settings_technical_status_callback, pattern="^settings_technical_status$"))
    application.add_handler(CallbackQueryHandler(settings_stats_callback, pattern="^settings_stats$"))
    application.add_handler(CallbackQueryHandler(settings_subscription_callback, pattern="^settings_subscription$"))
    application.add_handler(CallbackQueryHandler(settings_web_login_callback, pattern="^settings_web_login$"))

    # Driver callbacks
    application.add_handler(CallbackQueryHandler(driver_menu_callback, pattern="^driver_menu$"))
    application.add_handler(CallbackQueryHandler(driver_section_callback, pattern="^driver_section:"))
    application.add_handler(CallbackQueryHandler(driver_list_template_callback, pattern="^driver_list_template:"))
    application.add_handler(CallbackQueryHandler(driver_vehicle_view_callback, pattern="^driver_vehicle_view:"))
    application.add_handler(CallbackQueryHandler(driver_vehicle_delete_confirm_callback, pattern="^driver_vehicle_delete_confirm:"))
    application.add_handler(CallbackQueryHandler(driver_vehicle_delete_callback, pattern="^driver_vehicle_delete:"))
    application.add_handler(CallbackQueryHandler(driver_fuel_history_callback, pattern="^driver_fuel_history:"))
    application.add_handler(CallbackQueryHandler(driver_fuel_view_callback, pattern="^driver_fuel_view:"))
    application.add_handler(CallbackQueryHandler(driver_fuel_delete_confirm_callback, pattern="^driver_fuel_delete_confirm:"))
    application.add_handler(CallbackQueryHandler(driver_fuel_delete_callback, pattern="^driver_fuel_delete:"))
    application.add_handler(CallbackQueryHandler(driver_expense_view_callback, pattern="^driver_expense_view:"))
    application.add_handler(CallbackQueryHandler(driver_expense_delete_confirm_callback, pattern="^driver_expense_delete_confirm:"))
    application.add_handler(CallbackQueryHandler(driver_expense_delete_callback, pattern="^driver_expense_delete:"))
    application.add_handler(CallbackQueryHandler(driver_document_view_callback, pattern="^driver_document_view:"))
    application.add_handler(CallbackQueryHandler(driver_document_delete_confirm_callback, pattern="^driver_document_delete_confirm:"))
    application.add_handler(CallbackQueryHandler(driver_document_delete_callback, pattern="^driver_document_delete:"))
    application.add_handler(CallbackQueryHandler(driver_service_view_callback, pattern="^driver_service_view:"))

    application.add_handler(CallbackQueryHandler(share_bot_callback, pattern="^share_bot$"))
    
    # === Message Handler for Main Menu ===
    application.add_handler(menu_button_handler)
    application.add_error_handler(error_handler)
    
    logger.info("Telegram bot application created")
    
    return application
