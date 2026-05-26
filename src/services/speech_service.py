"""Speech-to-text service for Telegram voice messages."""

from dataclasses import dataclass
from typing import Any, Optional

import httpx

from src.config import settings


class SpeechTranscriptionUnavailable(RuntimeError):
    """Raised when voice transcription is disabled or not configured."""


class SpeechTranscriptionError(RuntimeError):
    """Raised when an external speech-to-text provider fails."""


@dataclass(frozen=True)
class SpeechTranscriptionResult:
    """Speech transcription output."""

    text: str
    provider: str
    model: str


class SpeechTranscriptionService:
    """OpenAI-compatible speech transcription client."""

    def __init__(self, config=settings):
        self.config = config

    def is_configured(self) -> bool:
        """Return whether transcription can be used."""
        return bool(
            self.config.VOICE_TRANSCRIPTION_ENABLED
            and self.config.OPENAI_API_KEY
        )

    def _model_candidates(self) -> list[str]:
        """Return primary model plus configured fallbacks without duplicates."""
        models = [self.config.VOICE_TRANSCRIPTION_MODEL.strip()]
        models.extend(
            raw.strip()
            for raw in self.config.VOICE_TRANSCRIPTION_FALLBACK_MODELS.split(",")
            if raw.strip()
        )

        unique: list[str] = []
        for model in models:
            if model and model not in unique:
                unique.append(model)
        return unique

    def _request_data(self, model: str) -> dict[str, str]:
        """Build provider request payload for a concrete model."""
        data = {
            "model": model,
            "response_format": "json",
        }
        if self.config.VOICE_TRANSCRIPTION_LANGUAGE:
            data["language"] = self.config.VOICE_TRANSCRIPTION_LANGUAGE
        if self.config.VOICE_TRANSCRIPTION_PROMPT:
            data["prompt"] = self.config.VOICE_TRANSCRIPTION_PROMPT
        return data

    @staticmethod
    def _provider_error_payload(response: httpx.Response) -> dict[str, Any]:
        """Return normalized provider error payload."""
        try:
            payload = response.json()
        except ValueError:
            return {}
        if not isinstance(payload, dict):
            return {}
        error = payload.get("error")
        return error if isinstance(error, dict) else payload

    @classmethod
    def _is_insufficient_quota(cls, response: httpx.Response) -> bool:
        """Return whether provider rejected the request because account quota is exhausted."""
        error = cls._provider_error_payload(response)
        code = str(error.get("code") or "").lower()
        error_type = str(error.get("type") or "").lower()
        message = str(error.get("message") or "").lower()
        return "insufficient_quota" in {code, error_type} or "quota" in message or "billing" in message

    @classmethod
    def _provider_error_message(cls, response: httpx.Response) -> str:
        """Map provider HTTP errors to safe user-facing Russian text."""
        status_code = response.status_code
        if status_code == 401:
            return "Ключ OpenAI API не принят. Проверьте OPENAI_API_KEY в .env."
        if status_code == 403:
            return "У ключа OpenAI API нет доступа к расшифровке аудио."
        if status_code == 413:
            return "Голосовое сообщение слишком большое для расшифровки."
        if status_code == 429:
            if cls._is_insufficient_quota(response):
                return (
                    "OpenAI API отклонил расшифровку из-за лимита или баланса аккаунта. "
                    "Проверьте Billing/Usage в OpenAI Platform."
                )
            return "Сервис расшифровки временно ограничил запросы. Попробуйте позже."
        if 500 <= status_code < 600:
            return "Сервис расшифровки временно недоступен. Попробуйте позже."
        return f"Сервис расшифровки вернул ошибку {status_code}."

    async def transcribe(
        self,
        audio_bytes: bytes,
        *,
        filename: str = "telegram_voice.ogg",
        content_type: str = "audio/ogg",
    ) -> SpeechTranscriptionResult:
        """Transcribe audio bytes through the configured provider."""
        if not self.is_configured():
            raise SpeechTranscriptionUnavailable(
                "Голосовая расшифровка не настроена. Укажите OPENAI_API_KEY и включите VOICE_TRANSCRIPTION_ENABLED."
            )
        if not audio_bytes:
            raise SpeechTranscriptionError("Пустой аудиофайл.")

        base_url = self.config.VOICE_TRANSCRIPTION_BASE_URL.rstrip("/")
        url = f"{base_url}/audio/transcriptions"
        headers = {"Authorization": f"Bearer {self.config.OPENAI_API_KEY}"}
        models = self._model_candidates()

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                response = None
                used_model = models[0]
                for index, model in enumerate(models):
                    files = {
                        "file": (filename, audio_bytes, content_type),
                    }
                    response = await client.post(
                        url,
                        headers=headers,
                        data=self._request_data(model),
                        files=files,
                    )
                    used_model = model
                    if response.status_code < 400:
                        break

                    can_fallback = (
                        response.status_code in {429, 500, 502, 503, 504}
                        and not self._is_insufficient_quota(response)
                        and index + 1 < len(models)
                    )
                    if not can_fallback:
                        break
        except httpx.HTTPError as exc:
            raise SpeechTranscriptionError("Не удалось подключиться к сервису расшифровки.") from exc

        if response is None:
            raise SpeechTranscriptionError("Не настроена модель расшифровки.")

        if response.status_code >= 400:
            raise SpeechTranscriptionError(self._provider_error_message(response))

        try:
            payload = response.json()
        except ValueError as exc:
            raise SpeechTranscriptionError("Сервис расшифровки вернул некорректный ответ.") from exc

        text = str(payload.get("text") or "").strip()
        if not text:
            raise SpeechTranscriptionError("Не удалось распознать текст в голосовом сообщении.")

        return SpeechTranscriptionResult(
            text=text,
            provider="openai-compatible",
            model=used_model,
        )
