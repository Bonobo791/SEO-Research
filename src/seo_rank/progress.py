"""stderr progress logging for long-running seo-rank run commands."""
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


import sys
from typing import TextIO


class RunProgress:
    """Write flushed, prefixed progress lines and a simple bar."""

    def __init__(
        self,
        stream: TextIO | None = None,
        *,
        enabled: bool = True,
        width: int = 20,
    ) -> None:
        self._stream = stream if stream is not None else sys.stderr
        self._enabled = enabled
        self._width = width

    def log(self, message: str) -> None:
        if not self._enabled:
            return
        print(f"[seo-rank] {message}", file=self._stream, flush=True)

    def keyword_log(self, keyword: str, step: str) -> None:
        self.log(f'keyword "{keyword}": {step}')

    def keyword_step(
        self,
        index: int,
        total: int,
        keyword: str,
        step: str,
    ) -> None:
        self.log(f'keyword {index}/{total} "{keyword}": {step}')
        self.progress(index, total)

    def progress(self, index: int, total: int) -> None:
        if not self._enabled:
            return
        completed = max(0, min(index, total)) if total > 0 else 0
        percent = 100 if total <= 0 else round((completed / total) * 100)
        filled = self._width if total <= 0 else round((completed / total) * self._width)
        filled = max(0, min(self._width, filled))
        bar = "#" * filled + "-" * (self._width - filled)
        print(
            f"[seo-rank] progress [{bar}] {completed}/{total} ({percent}%)",
            file=self._stream,
            flush=True,
        )
