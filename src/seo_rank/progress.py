"""stderr progress logging for long-running seo-rank run commands."""

import sys
from typing import TextIO


class RunProgress:
    """Write flushed, prefixed progress lines to stderr (or a test sink)."""

    def __init__(self, stream: TextIO | None = None, *, enabled: bool = True) -> None:
        self._stream = stream if stream is not None else sys.stderr
        self._enabled = enabled

    def log(self, message: str) -> None:
        if not self._enabled:
            return
        print(f"[seo-rank] {message}", file=self._stream, flush=True)

    def keyword_step(
        self,
        index: int,
        total: int,
        keyword: str,
        step: str,
    ) -> None:
        self.log(f'keyword {index}/{total} "{keyword}": {step}')
