from pathlib import Path

import polars as pl

from seo_rank.data.scans import scan_raw_responses
from seo_rank.data.validate import validate_required_columns


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
    assert lazy_frame.collect().to_dicts() == [
        {
            "run_id": "run-1",
            "response_id": "abc123",
            "endpoint": "serp",
        }
    ]


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
