"""Parse dictated list text into a safe list preview."""

from dataclasses import dataclass
import re
from typing import Iterable, Optional


@dataclass(frozen=True)
class VoiceListPreview:
    """Parsed voice list preview."""

    title: str
    items: list[str]
    transcript: str


class VoiceListParserService:
    """Convert free-form dictated text into list title and item lines."""

    DEFAULT_TITLE = "Голосовой список"

    _ENUM_WORDS = (
        "первое",
        "первый",
        "во-первых",
        "второе",
        "второй",
        "третье",
        "третий",
        "четвертое",
        "четвертый",
        "пятое",
        "пятый",
        "шестое",
        "шестой",
        "седьмое",
        "седьмой",
        "восьмое",
        "восьмой",
        "девятое",
        "девятый",
        "десятое",
        "десятый",
        "следующее",
        "дальше",
        "затем",
        "потом",
    )

    def parse(self, transcript: str, max_items: int = 40) -> VoiceListPreview:
        """Parse transcript into a preview title and item list."""
        normalized = self._normalize(transcript)
        title, body = self._extract_title(normalized)
        items = self._parse_items(body, max_items=max_items)
        return VoiceListPreview(
            title=title or self.DEFAULT_TITLE,
            items=items,
            transcript=normalized,
        )

    def _extract_title(self, text: str) -> tuple[str, str]:
        """Extract an optional title before a colon."""
        if ":" not in text:
            return self.DEFAULT_TITLE, text

        prefix, body = text.split(":", 1)
        prefix = re.sub(r"\s+", " ", prefix).strip(" \t\r\n-–—•.")
        body = body.strip()
        if not body or len(prefix) > 80:
            return self.DEFAULT_TITLE, text

        if re.search(r"\b(список|дела|покупки|задачи)\b", prefix, flags=re.IGNORECASE):
            return prefix[:80], body
        return self.DEFAULT_TITLE, text

    def _parse_items(self, text: str, max_items: int) -> list[str]:
        """Split text into item lines."""
        prepared = text
        enum_pattern = r"\b(?:" + "|".join(re.escape(word) for word in self._ENUM_WORDS) + r")\b"
        prepared = re.sub(enum_pattern, "\n", prepared, flags=re.IGNORECASE)
        prepared = re.sub(r"(?<!\d)\b\d{1,2}[\).\s]+", "\n", prepared)
        prepared = re.sub(r"\s+(?:и еще|ещё|еще)\s+", "\n", prepared, flags=re.IGNORECASE)
        prepared = re.sub(r"[;,\n]+", "\n", prepared)

        items = [item for item in self._cleanup_items(prepared.splitlines()) if item]
        return self._deduplicate(items)[:max_items]

    def _cleanup_items(self, parts: Iterable[str]) -> list[str]:
        """Clean up list item candidates."""
        result = []
        for part in parts:
            item = self._cleanup_item(part)
            if item:
                result.append(item)
        return result

    def _cleanup_item(self, value: str) -> str:
        """Normalize one item line."""
        item = re.sub(r"\s+", " ", value).strip(" \t\r\n-–—•")
        item = re.sub(
            r"^(?:создай|создать|сделай|составь|запиши|добавь|надо|нужно|мне нужно)\s+",
            "",
            item,
            flags=re.IGNORECASE,
        )
        item = re.sub(r"^(?:список|пункт|пункты|дела|покупки)\s+", "", item, flags=re.IGNORECASE)
        item = item.strip(" .")
        return item[:500]

    def _deduplicate(self, items: list[str]) -> list[str]:
        """Preserve order while removing exact duplicates."""
        seen = set()
        result = []
        for item in items:
            key = item.casefold()
            if key in seen:
                continue
            seen.add(key)
            result.append(item)
        return result

    def _normalize(self, text: Optional[str]) -> str:
        """Normalize ASR text for parser use."""
        return re.sub(r"\s+", " ", (text or "").replace("\r", "\n")).strip()
