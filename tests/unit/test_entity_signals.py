import polars as pl

from seo_rank.cli import main
from seo_rank.data.features import build_entity_signals_lazyframe


def test_entity_signals_builds_page_level_presence_and_provenance() -> None:
    entities = pl.DataFrame(
        {
            "run_id": ["run-1", "run-1"],
            "target_keyword_id": ["kw-1", "kw-1"],
            "target_keyword": ["keyword", "keyword"],
            "canonical_url_hash": ["url-a", "url-a"],
            "url": ["https://a.example/page", "https://a.example/page"],
            "entity_id": ["entity-a", "entity-a"],
            "matched_text": ["Alpha", "A"],
            "confidence": [2.0, 4.0],
            "relevance": [0.2, 0.6],
            "types": [["Topic"], ["Concept"]],
        }
    ).lazy()
    page_metrics = pl.DataFrame(
        {
            "run_id": ["run-1", "run-1"],
            "target_keyword_id": ["kw-1", "kw-1"],
            "target_keyword": ["keyword", "keyword"],
            "canonical_url_hash": ["url-a", "url-b"],
            "url": ["https://a.example/page", "https://b.example/page"],
            "textrazor_entities_present": [True, False],
        }
    ).lazy()
    serp_items = pl.DataFrame(
        {
            "run_id": ["run-1", "run-1"],
            "target_keyword_id": ["kw-1", "kw-1"],
            "canonical_url_hash": ["url-a", "url-b"],
            "url": ["https://a.example/page", "https://b.example/page"],
            "serp_rank": [1, 2],
        }
    ).lazy()

    result = build_entity_signals_lazyframe(entities, page_metrics, serp_items).collect()

    assert result.to_dicts() == [
        {
            "run_id": "run-1",
            "target_keyword_id": "kw-1",
            "target_keyword": "keyword",
            "canonical_url_hash": "url-a",
            "url": "https://a.example/page",
            "serp_rank": 1,
            "entity_id": "entity-a",
            "matched_texts": ["A", "Alpha"],
            "entity_types": ["Concept", "Topic"],
            "entity_present": 1,
            "entity_mention_count": 2,
            "entity_confidence_mean": 3.0,
            "entity_relevance_mean": 0.4,
            "schema_version": "feature_marts.v3",
        },
        {
            "run_id": "run-1",
            "target_keyword_id": "kw-1",
            "target_keyword": "keyword",
            "canonical_url_hash": "url-b",
            "url": "https://b.example/page",
            "serp_rank": 2,
            "entity_id": "entity-a",
            "matched_texts": [],
            "entity_types": [],
            "entity_present": 0,
            "entity_mention_count": 0,
            "entity_confidence_mean": None,
            "entity_relevance_mean": None,
            "schema_version": "feature_marts.v3",
        },
    ]


def test_entity_signals_keeps_best_rank_for_duplicate_serp_url() -> None:
    entities = pl.DataFrame(
        {
            "run_id": ["run-1"],
            "target_keyword_id": ["kw-1"],
            "target_keyword": ["keyword"],
            "canonical_url_hash": ["url-a"],
            "url": ["https://a.example/page"],
            "entity_id": ["entity-a"],
            "matched_text": ["Alpha"],
            "confidence": [2.0],
            "relevance": [0.2],
            "types": [["Topic"]],
        }
    ).lazy()
    page_metrics = pl.DataFrame(
        {
            "run_id": ["run-1"],
            "target_keyword_id": ["kw-1"],
            "target_keyword": ["keyword"],
            "canonical_url_hash": ["url-a"],
            "url": ["https://a.example/page"],
        }
    ).lazy()
    serp_items = pl.DataFrame(
        {
            "run_id": ["run-1", "run-1"],
            "target_keyword_id": ["kw-1", "kw-1"],
            "canonical_url_hash": ["url-a", "url-a"],
            "url": ["https://a.example/page", "https://a.example/page"],
            "serp_rank": [4, 2],
        }
    ).lazy()

    result = build_entity_signals_lazyframe(entities, page_metrics, serp_items).collect()

    assert result.select(["canonical_url_hash", "entity_id", "serp_rank"]).to_dicts() == [
        {"canonical_url_hash": "url-a", "entity_id": "entity-a", "serp_rank": 2}
    ]


def test_build_features_materializes_entity_signals(tmp_path) -> None:
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

    entity_signals = pl.read_parquet(run_dir / "parquet" / "entity_signals" / "part-0.parquet")

    assert entity_signals.schema["matched_texts"] == pl.List(pl.Utf8)
    assert entity_signals.schema["entity_types"] == pl.List(pl.Utf8)
    assert set(entity_signals["entity_present"].to_list()) <= {0, 1}
