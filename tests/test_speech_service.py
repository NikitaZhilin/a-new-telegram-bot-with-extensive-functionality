"""Tests for OpenAI-compatible speech transcription service."""

from types import SimpleNamespace

import httpx
import pytest

from src.services import speech_service as speech_module
from src.services.speech_service import SpeechTranscriptionError, SpeechTranscriptionService


def _config(**overrides):
    values = {
        "VOICE_TRANSCRIPTION_ENABLED": True,
        "OPENAI_API_KEY": "test-key",
        "VOICE_TRANSCRIPTION_BASE_URL": "https://api.example.test/v1",
        "VOICE_TRANSCRIPTION_MODEL": "gpt-4o-mini-transcribe",
        "VOICE_TRANSCRIPTION_FALLBACK_MODELS": "whisper-1",
        "VOICE_TRANSCRIPTION_LANGUAGE": "ru",
        "VOICE_TRANSCRIPTION_PROMPT": "",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.asyncio
async def test_transcription_falls_back_after_rate_limit(monkeypatch):
    """A temporary 429 should try the fallback model before failing the voice flow."""
    calls: list[str] = []

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, *, headers, data, files):
            calls.append(data["model"])
            if len(calls) == 1:
                return httpx.Response(
                    429,
                    json={"error": {"type": "rate_limit_exceeded", "message": "rate limited"}},
                )
            return httpx.Response(200, json={"text": "молоко\nхлеб"})

    monkeypatch.setattr(speech_module.httpx, "AsyncClient", FakeClient)

    result = await SpeechTranscriptionService(_config()).transcribe(b"voice")

    assert calls == ["gpt-4o-mini-transcribe", "whisper-1"]
    assert result.text == "молоко\nхлеб"
    assert result.model == "whisper-1"


@pytest.mark.asyncio
async def test_transcription_reports_quota_error_without_extra_fallback(monkeypatch):
    """Billing/quota 429 should show an actionable message instead of a bare status code."""
    calls: list[str] = []

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, *, headers, data, files):
            calls.append(data["model"])
            return httpx.Response(
                429,
                json={
                    "error": {
                        "code": "insufficient_quota",
                        "type": "insufficient_quota",
                        "message": "You exceeded your current quota.",
                    }
                },
            )

    monkeypatch.setattr(speech_module.httpx, "AsyncClient", FakeClient)

    with pytest.raises(SpeechTranscriptionError, match="лимит|баланс|Billing"):
        await SpeechTranscriptionService(_config()).transcribe(b"voice")

    assert calls == ["gpt-4o-mini-transcribe"]
