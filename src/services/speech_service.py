"""Speech-to-text service for Telegram voice messages."""

from dataclasses import dataclass
from typing import Optional

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
        data = {
            "model": self.config.VOICE_TRANSCRIPTION_MODEL,
            "response_format": "json",
        }
        if self.config.VOICE_TRANSCRIPTION_LANGUAGE:
            data["language"] = self.config.VOICE_TRANSCRIPTION_LANGUAGE
        if self.config.VOICE_TRANSCRIPTION_PROMPT:
            data["prompt"] = self.config.VOICE_TRANSCRIPTION_PROMPT

        headers = {"Authorization": f"Bearer {self.config.OPENAI_API_KEY}"}
        files = {
            "file": (filename, audio_bytes, content_type),
        }

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.post(url, headers=headers, data=data, files=files)
        except httpx.HTTPError as exc:
            raise SpeechTranscriptionError("Не удалось подключиться к сервису расшифровки.") from exc

        if response.status_code >= 400:
            raise SpeechTranscriptionError(
                f"Сервис расшифровки вернул ошибку {response.status_code}."
            )

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
            model=self.config.VOICE_TRANSCRIPTION_MODEL,
        )
