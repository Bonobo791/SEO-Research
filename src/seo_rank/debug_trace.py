"""Session-scoped NDJSON debug tracing for Cursor debug mode."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

DEBUG_LOG_PATH = Path(__file__).resolve().parents[2] / ".cursor" / "debug-a1b1a7.log"
SESSION_ID = "a1b1a7"


def debug_trace(
    *,
    hypothesis_id: str,
    location: str,
    message: str,
    data: dict[str, Any] | None = None,
    run_id: str = "pre-fix",
) -> None:
    # #region agent log
    payload = {
        "sessionId": SESSION_ID,
        "runId": run_id,
        "hypothesisId": hypothesis_id,
        "location": location,
        "message": message,
        "data": data or {},
        "timestamp": int(time.time() * 1000),
    }
    DEBUG_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with DEBUG_LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, default=str) + "\n")
    # #endregion
