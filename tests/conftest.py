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
from pathlib import Path


import pytest

from seo_rank.domain_blocklist import DomainBlocklist
from seo_rank.env import ensure_project_env_loaded

ensure_project_env_loaded()


@pytest.fixture(autouse=True)
def isolate_implicit_domain_blocklist(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Keep implicit blocklist writes out of the committed production file."""
    original_load = DomainBlocklist.load.__func__

    def load_test_blocklist(
        cls: type[DomainBlocklist], path: Path | str | None = None
    ) -> DomainBlocklist:
        return original_load(cls, tmp_path / "blocklist.txt" if path is None else path)

    monkeypatch.setattr(DomainBlocklist, "load", classmethod(load_test_blocklist))
