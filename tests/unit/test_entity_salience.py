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
import math


import polars as pl
import pytest

from seo_rank.cli import main
from seo_rank.data.features import (
    build_entity_linkage_aggregates,
    build_entity_salience_aggregates,
    build_textrazor_page_metrics_lazyframe,
)


def _entities_frame() -> pl.LazyFrame:
    return pl.DataFrame(
        {
            "run_id": ["run-1"] * 4,
            "target_keyword_id": ["kw-1"] * 4,
            "target_keyword": ["keyword"] * 4,
            "canonical_url_hash": ["url-a"] * 4,
            "url": ["https://a.example/page"] * 4,
            "entity_id": ["entity-a", "entity-a", "entity-b", "entity-c"],
            "matched_text": ["Alpha", "A", "Beta", "Gamma"],
            "confidence": [2.0, 4.0, 3.0, 1.0],
            "relevance": [0.2, 0.4, 0.6, 0.4],
            "types": [["Topic"], ["Concept"], ["Topic"], ["Other"]],
            "entity_english_id": ["alpha", "alpha", "beta", "gamma"],
            "wikidata_id": ["Q1", None, None, None],
            "wiki_link": [None, None, "https://example.com/wiki/Beta", None],
            "freebase_types": [[], [], [], []],
            "enriched_data_keys": [[], [], [], []],
        }
    ).lazy()


def _page_metrics_frame() -> pl.LazyFrame:
    return pl.DataFrame(
        {
            "run_id": ["run-1", "run-1"],
            "target_keyword_id": ["kw-1", "kw-1"],
            "target_keyword": ["keyword", "keyword"],
            "canonical_url_hash": ["url-a", "url-b"],
            "url": ["https://a.example/page", "https://b.example/page"],
            "textrazor_entities_present": [True, False],
        }
    ).lazy()


def test_entity_salience_aggregates_compute_page_level_stats() -> None:
    result = build_entity_salience_aggregates(_entities_frame()).collect()

    assert result.to_dicts() == [
        {
            "run_id": "run-1",
            "target_keyword_id": "kw-1",
            "target_keyword": "keyword",
            "canonical_url_hash": "url-a",
            "url": "https://a.example/page",
            # per-entity mean relevance: a=0.3 (2 mentions), b=0.6, c=0.4
            "textrazor_entity_salience_mean": pytest.approx(1.3 / 3),
            "textrazor_entity_salience_median": pytest.approx(0.4),
            "textrazor_entity_salience_top3_max": pytest.approx(0.6),
            "textrazor_entity_salience_mention_weighted": pytest.approx(0.4),
            "textrazor_salience_unique_entity_count": 3,
        }
    ]


def test_entity_linkage_aggregates_use_unique_entities_and_type_entropy() -> None:
    result = build_entity_linkage_aggregates(_entities_frame()).collect()

    assert result.to_dicts() == [
        {
            "run_id": "run-1",
            "target_keyword_id": "kw-1",
            "target_keyword": "keyword",
            "canonical_url_hash": "url-a",
            "url": "https://a.example/page",
            "textrazor_linked_entity_fraction": pytest.approx(2 / 3),
            "textrazor_entity_type_entropy": pytest.approx(
                -(0.5 * math.log(0.5) + 2 * 0.25 * math.log(0.25))
            ),
        }
    ]


def test_textrazor_page_metrics_join_fills_empty_pages() -> None:
    result = build_textrazor_page_metrics_lazyframe(
        _page_metrics_frame(), _entities_frame()
    ).collect()

    rows = {row["canonical_url_hash"]: row for row in result.to_dicts()}
    populated = rows["url-a"]
    assert populated["textrazor_entity_salience_mean"] == pytest.approx(1.3 / 3)
    assert populated["textrazor_salience_unique_entity_count"] == 3
    assert populated["textrazor_linked_entity_fraction"] == pytest.approx(2 / 3)
    assert populated["textrazor_entity_type_entropy"] is not None

    empty = rows["url-b"]
    assert empty["textrazor_entity_salience_mean"] is None
    assert empty["textrazor_entity_salience_median"] is None
    assert empty["textrazor_entity_salience_top3_max"] is None
    assert empty["textrazor_entity_salience_mention_weighted"] is None
    assert empty["textrazor_salience_unique_entity_count"] == 0
    assert empty["textrazor_linked_entity_fraction"] is None
    assert empty["textrazor_entity_type_entropy"] is None


def test_textrazor_page_metrics_join_does_not_duplicate_rows() -> None:
    result = build_textrazor_page_metrics_lazyframe(
        _page_metrics_frame(), _entities_frame()
    ).collect()

    assert result.height == 2
    assert result.select(
        ["run_id", "target_keyword_id", "canonical_url_hash"]
    ).unique().height == 2


def test_build_features_materializes_entity_salience_columns(tmp_path) -> None:
    run_dir = tmp_path / "run"
    assert (
        main(
            [
                "run",
                "--seed",
                "technical seo",
                "--dry-run",
                "--output-dir",
                str(run_dir),
            ]
        )
        == 0
    )

    metrics = pl.read_parquet(
        run_dir / "parquet" / "textrazor_page_metrics" / "part-0.parquet"
    )

    salience_columns = [
        "textrazor_entity_salience_mean",
        "textrazor_entity_salience_median",
        "textrazor_entity_salience_top3_max",
        "textrazor_entity_salience_mention_weighted",
        "textrazor_salience_unique_entity_count",
    ]
    for column in salience_columns:
        assert column in metrics.columns
    for column in salience_columns[:4]:
        values = metrics[column].drop_nulls()
        assert ((values >= 0) & (values <= 1)).all()
    assert (metrics["textrazor_salience_unique_entity_count"] >= 0).all()
