import polars as pl

from seo_rank.stats.artifacts import write_entity_stats_artifact
from seo_rank.stats.entities import summarize_entity_signals


def test_entity_stats_marks_eligible_presence_association_and_corrects_by_metric() -> None:
    rows = []
    for keyword_index in range(10):
        for rank in range(1, 21):
            rows.append(
                {
                    "entity_id": "entity-a",
                    "target_keyword_id": f"kw-{keyword_index}",
                    "target_keyword": f"keyword {keyword_index}",
                    "url": f"https://example.com/{keyword_index}/{rank}",
                    "serp_rank": rank,
                    "entity_present": int(rank <= 5),
                    "entity_mention_count": int(rank <= 5),
                    "entity_confidence_mean": 4.0 if rank <= 5 else None,
                    "entity_relevance_mean": 0.9 if rank <= 5 else None,
                    "matched_texts": ["Alpha"] if rank <= 5 else [],
                    "entity_types": ["Topic"] if rank <= 5 else [],
                }
            )

    results = summarize_entity_signals(pl.DataFrame(rows))

    presence = results.filter(pl.col("metric") == "entity_present").row(0, named=True)
    assert presence["entity_id"] == "entity-a"
    assert presence["status"] == "significant"
    assert presence["median_spearman_rho"] < 0
    assert presence["bh_q_value"] is not None
    assert presence["ols_covariance"] == "cluster"
    assert presence["example_urls"] == [
        "https://example.com/0/1",
        "https://example.com/1/1",
        "https://example.com/2/1",
    ]
    assert presence["rank_depth_key"] == "top_20"


def test_entity_stats_artifact_writes_parquet_and_report_summary(tmp_path) -> None:
    signals = pl.DataFrame(
        {
            "entity_id": ["entity-a"] * 10,
            "target_keyword_id": [f"kw-{index}" for index in range(10)],
            "target_keyword": [f"keyword {index}" for index in range(10)],
            "url": [f"https://example.com/{index}" for index in range(10)],
            "serp_rank": [1] * 10,
            "entity_present": [1] * 10,
            "entity_mention_count": [1] * 10,
            "entity_confidence_mean": [4.0] * 10,
            "entity_relevance_mean": [0.9] * 10,
            "matched_texts": [["Alpha"]] * 10,
            "entity_types": [["Topic"]] * 10,
        }
    )
    run_dir = tmp_path / "run"
    (run_dir / "parquet" / "entity_signals").mkdir(parents=True)
    signals.write_parquet(run_dir / "parquet" / "entity_signals" / "part-0.parquet")

    summary, report = write_entity_stats_artifact(run_dir)

    assert (run_dir / "stats" / "entity_stats.parquet").exists()
    assert summary["row_count"] == 4
    assert "-log(rank)" in report


def test_entity_stats_counts_distinct_present_pages_and_keeps_underpowered_descriptives() -> None:
    rows = []
    for keyword_index in range(2):
        for rank in range(1, 21):
            rows.append(
                {
                    "entity_id": "entity-a",
                    "target_keyword_id": f"kw-{keyword_index}",
                    "target_keyword": f"keyword {keyword_index}",
                    "canonical_url_hash": f"url-{keyword_index}-{rank}",
                    "url": f"https://example.com/{keyword_index}/{rank}",
                    "serp_rank": rank,
                    "entity_present": int(rank <= 5),
                    "entity_mention_count": int(rank <= 5),
                    "entity_confidence_mean": 4.0 if rank <= 5 else None,
                    "entity_relevance_mean": 0.9 if rank <= 5 else None,
                    "matched_texts": ["Alpha"] if rank <= 5 else [],
                    "entity_types": ["Topic"] if rank <= 5 else [],
                }
            )
    duplicate = dict(rows[0])
    duplicate["url"] = "https://mirror.example/duplicate"
    rows.extend([duplicate] * 20)

    results = summarize_entity_signals(pl.DataFrame(rows))

    presence = results.filter(pl.col("metric") == "entity_present").row(0, named=True)
    assert presence["present_page_count"] == 10
    assert presence["present_keyword_count"] == 2
    assert presence["usable_page_count"] == 40
    assert presence["status"] == "underpowered"
    assert presence["median_spearman_rho"] is not None
    assert presence["spearman_p_value"] is not None
    assert presence["bh_q_value"] is None


def test_entity_stats_report_includes_matched_text_provenance(tmp_path) -> None:
    rows = []
    for keyword_index in range(10):
        for rank in range(1, 21):
            rows.append(
                {
                    "entity_id": "entity-a",
                    "target_keyword_id": f"kw-{keyword_index}",
                    "target_keyword": f"keyword {keyword_index}",
                    "url": f"https://example.com/{keyword_index}/{rank}",
                    "serp_rank": rank,
                    "entity_present": int(rank <= 5),
                    "entity_mention_count": int(rank <= 5),
                    "entity_confidence_mean": 4.0 if rank <= 5 else None,
                    "entity_relevance_mean": 0.9 if rank <= 5 else None,
                    "matched_texts": ["Alpha"] if rank <= 5 else [],
                    "entity_types": ["Topic"] if rank <= 5 else [],
                }
            )
    run_dir = tmp_path / "run"
    (run_dir / "parquet" / "entity_signals").mkdir(parents=True)
    pl.DataFrame(rows).write_parquet(run_dir / "parquet" / "entity_signals" / "part-0.parquet")

    _, report = write_entity_stats_artifact(run_dir)

    assert "Alpha" in report
    assert "https://example.com/0/1" in report
