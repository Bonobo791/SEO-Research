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
from seo_rank.dataforseo import fixture_serp_response, normalize_serp_results



def test_normalize_serp_results_keeps_organic_rows_capped_at_depth() -> None:
    response = fixture_serp_response("technical seo")

    results = normalize_serp_results(response, keyword="technical seo", depth=20)

    assert len(results) == 20
    assert results[0] == {
        "keyword": "technical seo",
        "rank": 1,
        "url": "https://example.com/technical-seo/1",
        "title": "Technical Seo Organic Result 1",
        "description": "Fixture organic result 1 for technical seo.",
    }
    assert results[-1]["rank"] == 20
    assert all(result["keyword"] == "technical seo" for result in results)
    assert all("sponsored" not in result["url"] for result in results)


def test_normalize_serp_results_rejects_bool_rank_group() -> None:
    response = fixture_serp_response("technical seo")
    response["tasks"][0]["result"][0]["items"][1]["rank_group"] = True

    results = normalize_serp_results(response, keyword="technical seo", depth=20)

    assert len(results) == 20
    assert results[0]["rank"] == 2
    assert all(type(result["rank"]) is int for result in results)
