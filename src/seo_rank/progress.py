"""stderr progress logging for long-running seo-rank run commands."""

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
