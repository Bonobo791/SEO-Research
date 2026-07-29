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


from seo_rank.cli import RunConfig, build_offline_payload
from seo_rank.dataforseo import normalize_keyword_expansion


def test_offline_payload_uses_single_keyword_default(tmp_path: Path) -> None:
    payload = build_offline_payload(
        RunConfig(
            seed="technical seo",
            location="United States",
            language="en",
            device="desktop",
            depth=3,
            output_dir=tmp_path,
            model_name="fixture-similarity-v1",
            dry_run=True,
            skip_textrazor=True,
        )
    )

    keywords = payload["keywords"]
    assert isinstance(keywords, list)
    assert len(keywords) == 1
    assert keywords[0] == "technical seo"
    assert "technical seo audit" not in keywords
    assert "technical seo topic 23" not in keywords

    raw_provider_data = payload["raw_provider_data"]
    assert isinstance(raw_provider_data, dict)
    dataforseo = raw_provider_data["dataforseo"]
    assert isinstance(dataforseo, dict)
    assert dataforseo["keyword_expansion"]["provider"] == "dataforseo"


def test_normalize_keyword_expansion_drops_duplicates_in_first_seen_order() -> None:
    response = {
        "tasks": [
            {
                "result": [
                    {"keyword": "technical seo audit"},
                    {"keyword": "technical seo checklist"},
                    {"keyword": "technical seo audit"},
                    {"keyword": "technical seo topic"},
                    {"keyword": "technical seo checklist"},
                ]
            }
        ]
    }

    keywords = normalize_keyword_expansion(
        response,
        seed="technical seo",
        limit=10,
    )

    assert keywords == [
        "technical seo",
        "technical seo audit",
        "technical seo checklist",
        "technical seo topic",
    ]
