import polars as pl
import pytest

from seo_rank.data.features import build_site_scale


SITE_METRICS = {
    "images_size": [10.0, 20.0, 30.0, 40.0],
    "scripts_size": [20.0, 30.0, 40.0, 50.0],
    "stylesheets_size": [30.0, 40.0, 50.0, 60.0],
    "total_transfer_size": [40.0, 50.0, 60.0, 70.0],
    "total_dom_size": [50.0, 60.0, 70.0, 80.0],
    "internal_links_count": [1.0, 2.0, 3.0, 4.0],
}


def test_build_site_scale_uses_unique_page_medians_and_standardized_mean() -> None:
    rows = []
    for index, domain in enumerate(("a.example", "b.example", "c.example", "d.example")):
        for page_index in range(2):
            row = {
                "run_id": "run-1",
                "domain": domain,
                "canonical_url_hash": f"{domain}-{page_index}",
            }
            row.update({column: values[index] + page_index for column, values in SITE_METRICS.items()})
            rows.append(row)
    duplicate = dict(rows[0])
    rows.append(duplicate)

    result = build_site_scale(pl.DataFrame(rows)).collect().sort("domain")

    assert result.columns == ["run_id", "domain", "site_scale"]
    assert result["site_scale"].to_list() == pytest.approx(
        [-1.255724, -0.271936, 0.465585, 1.062075], abs=0.000001
    )


def test_build_site_scale_is_null_when_a_domain_component_is_missing() -> None:
    rows = []
    for index, domain in enumerate(("a.example", "b.example")):
        row = {
            "run_id": "run-1",
            "domain": domain,
            "canonical_url_hash": f"{domain}-1",
        }
        row.update({column: values[index] for column, values in SITE_METRICS.items()})
        rows.append(row)
    rows[1]["total_dom_size"] = None

    result = build_site_scale(pl.DataFrame(rows)).collect().sort("domain")

    assert result["site_scale"].to_list()[0] is not None
    assert result["site_scale"].to_list()[1] is None
