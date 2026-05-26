"""Tests for voice-to-list parsing and transcription config."""

from types import SimpleNamespace

import pytest

from src.services.speech_service import SpeechTranscriptionService, SpeechTranscriptionUnavailable
from src.services.voice_list_parser import VoiceListParserService


def test_voice_list_parser_extracts_title_and_items():
    """Dictated list text should become a title and clean item lines."""
    preview = VoiceListParserService().parse(
        "Список на завтра: первое купить молоко, второе забрать заказ, дальше позвонить врачу",
        max_items=10,
    )

    assert preview.title == "Список на завтра"
    assert preview.items == ["купить молоко", "забрать заказ", "позвонить врачу"]


def test_voice_list_parser_deduplicates_and_limits_items():
    """Parser should keep item order, remove duplicates, and respect limits."""
    preview = VoiceListParserService().parse(
        "хлеб, молоко, хлеб, яйца",
        max_items=2,
    )

    assert preview.items == ["хлеб", "молоко"]


@pytest.mark.asyncio
async def test_speech_service_requires_explicit_configuration():
    """Speech transcription must be disabled unless provider credentials are configured."""
    service = SpeechTranscriptionService(
        SimpleNamespace(
            VOICE_TRANSCRIPTION_ENABLED=False,
            OPENAI_API_KEY=None,
            VOICE_TRANSCRIPTION_BASE_URL="https://api.openai.com/v1",
            VOICE_TRANSCRIPTION_MODEL="gpt-4o-mini-transcribe",
            VOICE_TRANSCRIPTION_LANGUAGE="ru",
            VOICE_TRANSCRIPTION_PROMPT="",
        )
    )

    assert service.is_configured() is False
    with pytest.raises(SpeechTranscriptionUnavailable):
        await service.transcribe(b"test")
