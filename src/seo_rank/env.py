"""Load project settings from a `.env` file."""

from __future__ import annotations

import os
from pathlib import Path

ENV_FILENAME = ".env"
_ENV_LOADED = False


def find_env_file(*, start: Path | None = None) -> Path | None:
    current = (start or Path.cwd()).resolve()
    for directory in [current, *current.parents]:
        candidate = directory / ENV_FILENAME
        if candidate.is_file():
            return candidate
        if (directory / "pyproject.toml").is_file():
            break
    return None


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" not in stripped:
            continue
        key, _, raw_value = stripped.partition("=")
        key = key.strip()
        if not key:
            continue
        value = raw_value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        values[key] = value
    return values


def load_project_env(*, start: Path | None = None, override: bool = True) -> Path | None:
    """Load `.env` into ``os.environ``. Returns the loaded file path, if any."""

    env_file = find_env_file(start=start)
    if env_file is None:
        return None
    for key, value in parse_env_file(env_file).items():
        if override or key not in os.environ:
            os.environ[key] = value
    return env_file


def ensure_project_env_loaded(*, start: Path | None = None, override: bool = True) -> Path | None:
    """Load `.env` once per process. Safe to call from CLI entrypoints and pytest."""

    global _ENV_LOADED
    if _ENV_LOADED:
        return find_env_file(start=start)
    loaded = load_project_env(start=start, override=override)
    _ENV_LOADED = True
    return loaded
