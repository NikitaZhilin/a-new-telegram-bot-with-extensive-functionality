"""Safe restart request queue for RememberMe-owned services."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from src.config import settings

ALLOWED_RESTART_TARGETS = frozenset({"api", "bot", "worker", "all"})
RESTART_CONFIRMATION = "restart:rememberme"


class RestartRequestNotSupportedError(RuntimeError):
    """Raised when this deployment has no restart request queue configured."""


class RestartRequestService:
    """Write allowlisted restart requests for a local RememberMe supervisor."""

    def __init__(self, *, request_dir: str | None = None) -> None:
        self.request_dir = request_dir if request_dir is not None else settings.RESTART_REQUEST_DIR

    def create_request(
        self,
        *,
        target: Literal["api", "bot", "worker", "all"],
        requested_by: str,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """Persist a restart request as JSON without executing system actions."""
        if target not in ALLOWED_RESTART_TARGETS:
            raise ValueError("unsupported restart target")
        if not self.request_dir:
            raise RestartRequestNotSupportedError("restart is not supported by this deployment")

        queue_dir = Path(self.request_dir).expanduser().resolve()
        queue_dir.mkdir(parents=True, exist_ok=True)

        requested_at = datetime.now(timezone.utc)
        operation_id = f"rememberme-{requested_at:%Y%m%d}-{uuid.uuid4().hex[:8]}"
        payload = {
            "operation_id": operation_id,
            "target": target,
            "requested_by": self._clean_text(requested_by, max_length=120),
            "reason": self._clean_text(reason or "", max_length=500),
            "requested_at": requested_at.isoformat(),
            "status": "queued",
        }

        final_path = queue_dir / f"{operation_id}.json"
        temp_path = queue_dir / f".{operation_id}.tmp"
        temp_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        temp_path.replace(final_path)

        return {
            "status": "accepted",
            "operation_id": operation_id,
            "target": target,
            "message": "restart scheduled",
        }

    @staticmethod
    def _clean_text(value: str, *, max_length: int) -> str:
        """Keep stored metadata readable and remove control characters."""
        cleaned = "".join(ch if ch.isprintable() else " " for ch in str(value).strip())
        return " ".join(cleaned.split())[:max_length]
