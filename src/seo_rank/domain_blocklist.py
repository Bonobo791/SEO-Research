"""Persistent blocklist of domains that never load.

A run reads the committed ``domain_blocklist.txt`` and drops any SERP result on a
listed domain before fetching. When a domain returns an OnPage 50402 status on
both the initial request and its retry, it is appended so future runs skip it.
See the module ``DOMAIN_BLOCKLIST_FILENAME``.
"""
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

import logging
from pathlib import Path
from typing import Sequence

DOMAIN_BLOCKLIST_FILENAME = "domain_blocklist.txt"

_HEADER = (
    "# Domains that failed to load. Auto-appended on failure; skipped on future runs.\n"
    "# Delete a line to re-enable a domain.\n"
)

logger = logging.getLogger("seo_rank.dataforseo.onpage")


def registrable_domain(url: str) -> str | None:
    """Return the lowercased host of ``url``, minus scheme/userinfo/port and a
    leading ``www.``. Returns ``None`` when no host can be parsed.

    Not a true public-suffix parse: ``sub.example.com`` normalizes to
    ``sub.example.com``, and matching (see :meth:`DomainBlocklist.is_blocked`)
    handles the subdomain case. Multi-part eTLDs (``co.uk``) are the user's
    responsibility when they list a domain.
    """

    host = url.strip().lower()
    if "://" in host:
        host = host.split("://", 1)[1]
    host = host.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
    host = host.split("@")[-1].split(":", 1)[0]
    host = host.removeprefix("www.")
    return host or None


def _resolve_default_path() -> Path:
    filename = Path(DOMAIN_BLOCKLIST_FILENAME)
    for parent in Path(__file__).resolve().parents:
        candidate = parent / filename
        if candidate.exists():
            return candidate
    # Not committed yet: default to the repo root two levels above this package
    # (src/seo_rank/ -> repo root), so the first append lands somewhere sensible.
    return Path(__file__).resolve().parents[2] / filename


class DomainBlocklist:
    """Loaded blocklist plus per-run append state."""

    def __init__(self, path: Path, blocked: set[str]) -> None:
        self.path = path
        self._blocked = blocked  # mutated as new domains are recorded this run

    @classmethod
    def load(cls, path: Path | str | None = None) -> "DomainBlocklist":
        resolved = Path(path) if path is not None else _resolve_default_path()
        blocked: set[str] = set()
        if resolved.exists():
            for raw in resolved.read_text(encoding="utf-8").splitlines():
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                entry = registrable_domain(line.split()[0])
                if entry:
                    blocked.add(entry)
        return cls(resolved, blocked)

    def is_blocked(self, url: str) -> bool:
        host = registrable_domain(url)
        if host is None:
            return False
        return any(host == entry or host.endswith("." + entry) for entry in self._blocked)

    def filter_results(
        self,
        results: Sequence[dict[str, object]],
        *,
        keyword: str = "",
        progress: object | None = None,
    ) -> list[dict[str, object]]:
        kept: list[dict[str, object]] = []
        for result in results:
            url = str(result.get("url", ""))
            if url and self.is_blocked(url):
                if progress is not None:
                    progress.keyword_log(
                        keyword, f"skipping blocked domain ({registrable_domain(url)})"
                    )
                continue
            kept.append(dict(result))
        return kept

    def record(self, url: str, *, keyword: str, reason: str) -> None:
        """Append ``url``'s registrable domain to the file if new, and skip it for
        the rest of this run. Idempotent within a run and against existing lines.

        ponytail: naive append + read-time dedup. Two concurrent runs can double
        -append a line; harmless since :meth:`load` dedups via a set. A single
        repeated timeout can permanently block a good domain — prune the line by
        hand; the trailing comment records why it was added.
        """

        domain = registrable_domain(url)
        if not domain or domain in self._blocked:
            return
        self._blocked.add(domain)
        keyword_note = keyword.replace('"', "'")
        line = f'{domain}  # keyword="{keyword_note}" reason={reason}\n'
        write_header = not self.path.exists() or self.path.stat().st_size == 0
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            if write_header:
                handle.write(_HEADER)
            handle.write(line)
        logger.warning(
            "blocklisted domain=%s keyword=%r reason=%s (url=%s)",
            domain,
            keyword,
            reason,
            url,
        )
