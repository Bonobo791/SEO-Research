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


from pathlib import Path

from seo_rank.domain_blocklist import DomainBlocklist


def test_tests_do_not_use_the_committed_domain_blocklist() -> None:
    tests_dir = Path(__file__).parents[1]
    offenders = [
        path
        for path in tests_dir.rglob("test_*.py")
        if path != Path(__file__) and (
            "domain_blocklist.txt" in path.read_text(encoding="utf-8")
            or "DomainBlocklist.load()" in path.read_text(encoding="utf-8")
        )
    ]

    assert offenders == []


def test_implicit_blocklist_path_is_test_local(tmp_path: Path) -> None:
    blocklist = DomainBlocklist.load()

    blocklist.record(
        "https://unavailable.example/path",
        keyword="test keyword",
        reason="test",
    )

    assert blocklist.path == tmp_path / "blocklist.txt"
    assert blocklist.path.read_text(encoding="utf-8").endswith(
        'unavailable.example  # keyword="test keyword" reason=test\n'
    )
