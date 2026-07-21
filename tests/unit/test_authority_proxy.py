import math

import polars as pl
import pytest

from seo_rank.data.features import (
    AUTHORITY_PROXY_BOOLEAN_COLUMNS,
    AUTHORITY_PROXY_BOOLEAN_INVERTED_COLUMNS,
    AUTHORITY_PROXY_COMPONENT_COLUMNS,
    AUTHORITY_PROXY_CONTINUOUS_COLUMNS,
    AUTHORITY_PROXY_MODELED_ONPAGE_COLUMNS,
    _onpage_frame_for_authority_proxy,
    build_analysis_panel_keyword_serp,
    build_authority_proxy,
)
from seo_rank.stats.spec import load_analysis_spec


def _component_defaults() -> dict[str, object]:
    """
    Build default feature values for authority-proxy components.
    
    Returns:
    	dict[str, object]: A mapping of continuous and boolean component columns to their baseline values.
    """
    row: dict[str, object] = {}
    for column in AUTHORITY_PROXY_CONTINUOUS_COLUMNS:
        row[column] = 10.0
    for column in AUTHORITY_PROXY_BOOLEAN_COLUMNS:
        row[column] = False
    for column in AUTHORITY_PROXY_BOOLEAN_INVERTED_COLUMNS:
        row[column] = True
    return row


def _row(run_id: str, domain: str, page_index: int, **overrides: object) -> dict[str, object]:
    """
    Create a feature row with identifiers, default component values, and optional overrides.
    
    Parameters:
    	run_id (str): Identifier for the run containing the row.
    	domain (str): Domain associated with the row.
    	page_index (int): Index used to construct the canonical URL hash.
    	overrides (object): Feature values that replace the corresponding defaults.
    
    Returns:
    	dict[str, object]: The assembled feature row.
    """
    row: dict[str, object] = {
        "run_id": run_id,
        "domain": domain,
        "canonical_url_hash": f"{domain}-{page_index}",
    }
    row.update(_component_defaults())
    row.update(overrides)
    return row


def test_build_authority_proxy_outputs_domain_float64_column() -> None:
    rows = [
        _row("run-1", domain, 0, time_to_first_byte_ms=10.0 + (index * 10.0))
        for index, domain in enumerate(("a.example", "b.example", "c.example", "d.example"))
    ]

    result = build_authority_proxy(pl.DataFrame(rows)).collect().sort("domain")

    assert result.columns == ["run_id", "domain", "authority_proxy"]
    assert result.schema["authority_proxy"] == pl.Float64
    assert result["authority_proxy"].null_count() == 0


def test_build_authority_proxy_excludes_modeled_onpage_signals() -> None:
    rows = [
        _row(
            "run-1",
            domain,
            0,
            onpage_score=90.0 - (index * 30.0),
            connection_time_ms=10.0 + (index * 50.0),
            is_redirect=index > 0,
        )
        for index, domain in enumerate(("a.example", "b.example", "c.example"))
    ]

    values = build_authority_proxy(pl.DataFrame(rows)).collect()["authority_proxy"]

    assert values.to_list() == pytest.approx([0.0, 0.0, 0.0])


def test_authority_proxy_excludes_every_registered_onpage_predictor() -> None:
    modeled_columns = frozenset(
        column
        for family in load_analysis_spec().signal_families.families_by_kind("onpage_metric")
        for column in family.signal_columns
    )

    assert AUTHORITY_PROXY_MODELED_ONPAGE_COLUMNS == modeled_columns
    assert modeled_columns.isdisjoint(AUTHORITY_PROXY_CONTINUOUS_COLUMNS)
    assert modeled_columns.isdisjoint(AUTHORITY_PROXY_BOOLEAN_COLUMNS)
    assert modeled_columns.isdisjoint(AUTHORITY_PROXY_BOOLEAN_INVERTED_COLUMNS)


def test_build_authority_proxy_ranks_worse_domains_lower() -> None:
    rows = [
        _row("run-1", "good.example", 0),
        _row(
            "run-1",
            "mid-a.example",
            0,
            time_to_first_byte_ms=60.0,
            no_title=True,
        ),
        _row(
            "run-1",
            "mid-b.example",
            0,
            time_to_first_byte_ms=120.0,
            no_title=True,
            is_broken=True,
        ),
        _row(
            "run-1",
            "bad.example",
            0,
            time_to_first_byte_ms=180.0,
            no_title=True,
            is_broken=True,
            is_4xx_code=True,
            canonical=False,
        ),
    ]

    result = build_authority_proxy(pl.DataFrame(rows)).collect().sort("domain")
    values = {
        row["domain"]: row["authority_proxy"] for row in result.to_dicts()
    }

    assert values["good.example"] > values["mid-a.example"]
    assert values["mid-a.example"] > values["mid-b.example"]
    assert values["mid-b.example"] > values["bad.example"]


def test_build_authority_proxy_uses_domain_boolean_rates() -> None:
    rows = [
        _row("run-1", "clean.example", 0),
        _row("run-1", "clean.example", 1),
        _row("run-1", "half.example", 0, no_title=True),
        _row("run-1", "half.example", 1),
        _row("run-1", "all.example", 0, no_title=True),
        _row("run-1", "all.example", 1, no_title=True),
    ]

    result = build_authority_proxy(pl.DataFrame(rows)).collect().sort("domain")
    values = {row["domain"]: row["authority_proxy"] for row in result.to_dicts()}

    assert values["clean.example"] > values["half.example"]
    assert values["half.example"] > values["all.example"]


def test_build_authority_proxy_uses_available_components_when_one_is_missing() -> None:
    rows = [
        _row("run-1", "a.example", 0),
        _row("run-1", "b.example", 0),
        _row("run-1", "c.example", 0),
    ]
    rows[1]["time_to_first_byte_ms"] = None

    result = build_authority_proxy(pl.DataFrame(rows)).collect().sort("domain")

    values = result["authority_proxy"].to_list()

    assert all(value is not None and math.isfinite(value) for value in values)


def test_build_authority_proxy_excludes_non_finite_values_from_window_statistics() -> None:
    rows = [
        _row("run-1", "a.example", 0, time_to_first_byte_ms=90.0),
        _row("run-1", "b.example", 0, time_to_first_byte_ms=70.0),
        _row("run-1", "c.example", 0, time_to_first_byte_ms=50.0),
        _row("run-1", "invalid.example", 0, time_to_first_byte_ms=float("inf")),
    ]

    values = build_authority_proxy(pl.DataFrame(rows)).collect()["authority_proxy"].to_list()

    assert all(value is not None and math.isfinite(value) for value in values)


def test_build_authority_proxy_is_null_when_no_component_is_available() -> None:
    rows = [
        _row("run-1", "a.example", 0),
        _row("run-1", "b.example", 0),
        _row("run-1", "c.example", 0),
    ]
    for column in (
        *AUTHORITY_PROXY_CONTINUOUS_COLUMNS,
        *AUTHORITY_PROXY_BOOLEAN_COLUMNS,
        *AUTHORITY_PROXY_BOOLEAN_INVERTED_COLUMNS,
    ):
        rows[1][column] = None

    result = build_authority_proxy(pl.DataFrame(rows)).collect().sort("domain")

    assert result["authority_proxy"].to_list()[1] is None


def test_build_authority_proxy_standardizes_within_run() -> None:
    domains = ("a.example", "b.example", "c.example", "d.example")
    rows: list[dict[str, object]] = []
    for run_id in ("run-1", "run-2"):
        for index, domain in enumerate(domains):
            rows.append(
                _row(
                    run_id,
                    domain,
                    0,
                    no_title=index >= 2,
                )
            )

    result = build_authority_proxy(pl.DataFrame(rows)).collect()

    for run_id in ("run-1", "run-2"):
        run_values = result.filter(pl.col("run_id") == run_id)["authority_proxy"].to_list()
        assert sum(run_values) == pytest.approx(0.0, abs=1e-9)

    run_one = {
        row["domain"]: row["authority_proxy"]
        for row in result.filter(pl.col("run_id") == "run-1").to_dicts()
    }
    run_two = {
        row["domain"]: row["authority_proxy"]
        for row in result.filter(pl.col("run_id") == "run-2").to_dicts()
    }
    for domain in domains:
        assert run_one[domain] == pytest.approx(run_two[domain], abs=1e-9)


def test_analysis_panel_drops_rows_with_null_authority_proxy() -> None:
    keyword_serp = pl.DataFrame(
        {
            "run_id": ["run-1", "run-1"],
            "target_keyword_id": ["kw-1", "kw-1"],
            "canonical_url_hash": ["hash-a", "hash-b"],
            "url": ["https://a.example/x", "https://b.example/y"],
        }
    )
    page_features = keyword_serp.clone()
    domain_features = pl.DataFrame(
        {
            "run_id": ["run-1", "run-1"],
            "domain": ["a.example", "b.example"],
            "site_scale": [0.5, 0.5],
            "authority_proxy": [0.5, None],
        }
    )

    result = build_analysis_panel_keyword_serp(
        keyword_serp.lazy(), page_features.lazy(), domain_features.lazy()
    ).collect()

    assert result["canonical_url_hash"].to_list() == ["hash-a"]

def test_onpage_frame_for_authority_proxy_null_fills_absent_component_columns() -> None:
    """Absent CWV columns are selected as null so build_authority_proxy can run."""
    join_keys = {
        "run_id": ["run-1"],
        "target_keyword_id": ["kw-1"],
        "canonical_url_hash": ["hash-a"],
        "url": ["https://a.example/x"],
    }
    present_components = [
        column
        for column in AUTHORITY_PROXY_COMPONENT_COLUMNS
        if column != "time_to_first_byte_ms"
    ]
    row = {**join_keys}
    for column in present_components:
        if column in AUTHORITY_PROXY_CONTINUOUS_COLUMNS:
            row[column] = [10.0]
        elif column in AUTHORITY_PROXY_BOOLEAN_COLUMNS:
            row[column] = [False]
        else:
            row[column] = [True]

    frame = pl.DataFrame(row).lazy()
    assert "time_to_first_byte_ms" not in frame.collect_schema()

    result = _onpage_frame_for_authority_proxy(frame).collect()

    assert "time_to_first_byte_ms" in result.columns
    assert result["time_to_first_byte_ms"].null_count() == 1
    for column in AUTHORITY_PROXY_COMPONENT_COLUMNS:
        assert column in result.columns

