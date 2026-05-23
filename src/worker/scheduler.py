"""
Legacy scheduler module (deprecated).

Use ReminderWorkerService from src.worker.reminder_worker instead.
This module is kept for backward compatibility.
"""

import warnings
from src.worker.reminder_worker import ReminderWorkerService, run_worker

warnings.warn(
    "src.worker.scheduler is deprecated. Use src.worker.reminder_worker instead.",
    DeprecationWarning,
    stacklevel=2,
)

# Re-export for backward compatibility
ReminderWorker = ReminderWorkerService

__all__ = ["ReminderWorker", "ReminderWorkerService", "run_worker"]
