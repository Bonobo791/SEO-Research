"""Load project settings from a `.env` file."""
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
