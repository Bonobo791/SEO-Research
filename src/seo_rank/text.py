"""Text normalization helpers for offline page text fixtures."""

import re
from collections.abc import Mapping
from typing import Any


def normalize_page_text(
    page: Mapping[str, Any],
    *,
    min_words: int = 5,
) -> list[dict[str, object]]:
    """Split parsed page text into stable, usable passage rows."""

    url = page.get("url")
    text = page.get("text", "")
    if not isinstance(url, str) or not isinstance(text, str):
        return []

    passages: list[dict[str, object]] = []
    for paragraph in paragraph_blocks(text):
        word_count = count_words(paragraph)
        if word_count < min_words:
            continue
        passages.append(
            {
                "url": url,
                "passage_id": f"{url}#p{len(passages) + 1}",
                "source": "page_text",
                "text": paragraph,
                "word_count": word_count,
            }
        )
    return passages


def paragraph_blocks(text: str) -> list[str]:
    blocks: list[str] = []
    for block in re.split(r"\n\s*\n+", text):
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        paragraph = normalize_whitespace(" ".join(lines))
        if paragraph:
            blocks.append(paragraph)
    return blocks


def normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def count_words(value: str) -> int:
    return len(re.findall(r"\b[\w'-]+\b", value))
