"""Text normalization helpers for offline page text fixtures."""
# SEO Research — SEO Factors Research Tool
# Copyright (C) 2026 Andrew Philip Weilbacher
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.
#
# Commercial licensing: contact@marketingprowess.simplelogin.com — see COMMERCIAL.md


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
