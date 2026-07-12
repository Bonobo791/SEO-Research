from pathlib import Path

import polars as pl

from seo_rank.data.normalize import build_curated_lazyframes
from seo_rank.data.scans import scan_curated_table, scan_raw_responses
from seo_rank.data.validate import (
    align_lazyframe_schema,
    validate_frame_contract,
    validate_materialized_frame_contract,
    validate_required_columns,
)


def test_scan_raw_responses_uses_lazy_parquet_scan(
    tmp_path: Path,
    monkeypatch,
) -> None:
    run_dir = tmp_path / "run-1"
    captured: dict[str, object] = {}

    def fake_scan_parquet(path: str, **kwargs):
        captured["path"] = path
        captured["kwargs"] = kwargs
        return pl.DataFrame(
            [
                {
                    "run_id": "run-1",
                    "response_id": "abc123",
                    "endpoint": "serp",
                }
            ]
        ).lazy()

    monkeypatch.setattr("seo_rank.data.scans.pl.scan_parquet", fake_scan_parquet)

    lazy_frame = scan_raw_responses(run_dir)

    assert isinstance(lazy_frame, pl.LazyFrame)
    assert captured["path"] == str(run_dir / "parquet" / "raw_responses")
    assert captured["kwargs"]["hive_partitioning"] is True
    assert captured["kwargs"]["missing_columns"] == "insert"
    assert lazy_frame.collect().to_dicts() == [
        {
            "run_id": "run-1",
            "response_id": "abc123",
            "endpoint": "serp",
            "request_metadata_json": None,
            "timestamp": None,
        }
    ]


def test_align_lazyframe_schema_backfills_missing_columns_with_nulls() -> None:
    frame = pl.DataFrame([{"run_id": "run-1", "onpage_score": 85.5}]).lazy()
    expected_schema = {
        "run_id": pl.Utf8,
        "onpage_score": pl.Float64,
        "title_length": pl.Int64,
    }

    aligned = align_lazyframe_schema(frame, expected_schema)
    collected = aligned.collect()

    assert "title_length" in collected.columns
    assert collected["title_length"].to_list() == [None]
    assert collected["onpage_score"].to_list() == [85.5]


def test_validate_required_columns_rejects_missing_columns() -> None:
    valid_frame = pl.DataFrame(
        [{"run_id": "run-1", "response_id": "abc123", "endpoint": "serp"}]
    ).lazy()

    assert validate_required_columns(
        valid_frame,
        required_columns={"run_id", "response_id", "endpoint"},
    ) is valid_frame

    missing_frame = pl.DataFrame([{"run_id": "run-1"}]).lazy()

    try:
        validate_required_columns(
            missing_frame,
            required_columns={"run_id", "response_id"},
        )
    except ValueError as error:
        assert "response_id" in str(error)
    else:
        raise AssertionError("expected ValueError")


def test_validate_frame_contract_checks_schema_keys_and_expected_schema() -> None:
    valid_frame = pl.DataFrame(
        [
            {
                "run_id": "run-1",
                "serp_item_id": "serp-1",
                "serp_rank": 1,
                "response_id": "resp-1",
            }
        ]
    ).lazy()

    assert validate_frame_contract(
        valid_frame,
        required_columns={"run_id", "serp_item_id", "serp_rank", "response_id"},
        expected_schema={
            "run_id": pl.Utf8,
            "serp_item_id": pl.Utf8,
            "serp_rank": pl.Int64,
            "response_id": pl.Utf8,
        },
    ) is valid_frame


def test_validate_frame_contract_does_not_collect_rows() -> None:
    lazy_frame = pl.DataFrame(
        [{"run_id": "run-1", "response_id": "abc123", "endpoint": "serp"}]
    ).lazy()

    def fail_collect(*args, **kwargs):  # noqa: ANN001, ANN003
        raise AssertionError("validate_frame_contract should not collect rows")

    original_collect = pl.LazyFrame.collect
    pl.LazyFrame.collect = fail_collect
    try:
        assert validate_frame_contract(
            lazy_frame,
            required_columns={"run_id", "response_id", "endpoint"},
            expected_schema={
                "run_id": pl.Utf8,
                "response_id": pl.Utf8,
                "endpoint": pl.Utf8,
            },
        ) is lazy_frame
    finally:
        pl.LazyFrame.collect = original_collect


def test_validate_materialized_frame_contract_checks_unique_nulls_and_ranges() -> None:
    valid_frame = pl.DataFrame(
        [
            {
                "run_id": "run-1",
                "serp_item_id": "serp-1",
                "serp_rank": 1,
                "response_id": "resp-1",
            }
        ]
    )

    assert validate_materialized_frame_contract(
        valid_frame,
        unique_columns={"serp_item_id"},
        non_null_columns={"serp_item_id", "serp_rank"},
        bounded_columns={"serp_rank": (1, 20)},
    ) is valid_frame

    invalid_frame = pl.DataFrame(
        [
            {
                "run_id": "run-1",
                "serp_item_id": "serp-1",
                "serp_rank": 0,
                "response_id": None,
            },
            {
                "run_id": "run-1",
                "serp_item_id": "serp-1",
                "serp_rank": 2,
                "response_id": "resp-2",
            },
        ]
    )

    try:
        validate_materialized_frame_contract(
            invalid_frame,
            unique_columns={"serp_item_id"},
            non_null_columns={"serp_item_id", "serp_rank", "response_id"},
            bounded_columns={"serp_rank": (1, 20)},
        )
    except ValueError as error:
        message = str(error)
        assert "serp_item_id" in message or "response_id" in message or "serp_rank" in message
    else:
        raise AssertionError("expected ValueError")


def test_build_curated_lazyframes_returns_lazyframes() -> None:
    frames = build_curated_lazyframes(
        {
            "keywords": [{"run_id": "run-1", "target_keyword": "technical seo"}],
            "pages": [{"run_id": "run-1", "url": "https://example.com"}],
        }
    )

    assert isinstance(frames["keywords"], pl.LazyFrame)
    assert isinstance(frames["pages"], pl.LazyFrame)



def test_scan_curated_table_raises_clear_error_when_dataset_has_no_parts(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "run-1"
    dataset_dir = run_dir / "parquet" / "analysis_mart"
    dataset_dir.mkdir(parents=True)

    try:
        scan_curated_table(run_dir, "analysis_mart").collect()
    except FileNotFoundError as error:
        message = str(error)
        assert "analysis_mart" in message
        assert "no parquet parts" in message
        assert "expanded paths were empty" not in message
    else:
        raise AssertionError("expected FileNotFoundError for empty dataset dir")
