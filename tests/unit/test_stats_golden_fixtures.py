from __future__ import annotations

import json
import math
from pathlib import Path

import polars as pl
import pytest

from seo_rank.stats.artifacts import run_phase5_stats
from seo_rank.stats.spec import load_analysis_spec


SIMILARITY_SCALES = {
    "bge": 4.0,
    "gemini_doc_retrieval": 2.0,
    "gemini_semantic_similarity": 1.0,
}

LOW_SIGNAL_OFFSETS = {
    "bge": 0.0,
    "gemini_doc_retrieval": 0.1,
    "gemini_semantic_similarity": 0.2,
}


def _analysis_mart_frame(
    *,
    mode: str = "confirmatory",
    keyword_count: int = 10,
    serp_count: int = 20,
    influential: bool = False,
) -> pl.DataFrame:
    rows: list[dict[str, object]] = []
    for keyword_index in range(1, keyword_count + 1):
        target_keyword_id = f"kw-{keyword_index}"
        target_keyword = f"keyword {keyword_index}"
        keyword_offset = keyword_index * 0.01
        for serp_rank in range(1, serp_count + 1):
            observed_rank = 1 if mode == "hard_fail" else serp_rank
            rank_signal = -math.log(observed_rank)
            if mode == "low_signal":
                shared_signal = keyword_offset + (0.02 if serp_rank % 2 == 0 else -0.02)
                bge_score = shared_signal + LOW_SIGNAL_OFFSETS["bge"]
                gemini_doc_score = shared_signal + LOW_SIGNAL_OFFSETS["gemini_doc_retrieval"]
                gemini_semantic_score = shared_signal + LOW_SIGNAL_OFFSETS["gemini_semantic_similarity"]
            elif mode == "collinear":
                shared_signal = 3.0 * rank_signal + keyword_offset
                bge_score = shared_signal
                gemini_doc_score = shared_signal
                gemini_semantic_score = shared_signal
            else:
                bge_score = SIMILARITY_SCALES["bge"] * rank_signal + keyword_offset
                gemini_doc_score = SIMILARITY_SCALES["gemini_doc_retrieval"] * rank_signal + keyword_offset
                gemini_semantic_score = (
                    SIMILARITY_SCALES["gemini_semantic_similarity"] * rank_signal + keyword_offset
                )
            if influential and keyword_index == 1 and serp_rank == 1:
                bge_score += 100.0

            rows.append(
                {
                    "run_id": "run-1",
                    "target_keyword_id": target_keyword_id,
                    "target_keyword": target_keyword,
                    "keyword_order": keyword_index,
                    "source_response_id": f"resp-{keyword_index}",
                    "serp_item_id": f"serp-{keyword_index}-{serp_rank}",
                    "page_id": f"page-{keyword_index}-{serp_rank}",
                    "response_id": f"page-resp-{keyword_index}-{serp_rank}",
                    "canonical_url_hash": f"url-{keyword_index}-{serp_rank}",
                    "url": f"https://example.com/{keyword_index}/{serp_rank}",
                    "serp_rank": observed_rank,
                    "title": f"title-{keyword_index}-{serp_rank}",
                    "description": f"description-{keyword_index}-{serp_rank}",
                    "page_text_length": 200 + (keyword_index * 3) + serp_rank,
                    "bge_raw_score": bge_score,
                    "bge_normalized_score": bge_score,
                    "gemini_doc_retrieval_raw_score": gemini_doc_score,
                    "gemini_doc_retrieval_normalized_score": gemini_doc_score,
                    "gemini_semantic_similarity_raw_score": gemini_semantic_score,
                    "gemini_semantic_similarity_normalized_score": gemini_semantic_score,
                    "schema_version": "analysis_mart.v1",
                }
            )
    return pl.DataFrame(rows)


def _run_phase5_stats(
    tmp_path: Path,
    frame: pl.DataFrame,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[object, dict[str, object], dict[str, object] | None, str]:
    run_dir = tmp_path / "runs" / "run-1"
    monkeypatch.setattr(
        "seo_rank.stats.panel.scan_curated_table",
        lambda path, table_name: frame.lazy(),
    )

    result = run_phase5_stats(run_dir)
    stats_dir = run_dir / "stats"
    summary = json.loads((stats_dir / "stats_summary.json").read_text(encoding="utf-8"))
    diagnostics_path = stats_dir / "stats_diagnostics.json"
    diagnostics = (
        json.loads(diagnostics_path.read_text(encoding="utf-8"))
        if diagnostics_path.exists()
        else None
    )
    report = (stats_dir / "stats_report.md").read_text(encoding="utf-8")
    return result, summary, diagnostics, report


def _assert_contract_metadata(summary: dict[str, object], spec) -> None:
    assert summary["analysis_spec_version"] == spec.version
    assert summary["estimand_version"] == spec.estimand_version
    assert summary["primary_backend"] == spec.primary_backend
    assert summary["backend_order"] == list(spec.backend_order)
    assert summary["metadata"]["analysis_spec_version"] == spec.version
    assert summary["metadata"]["estimand_version"] == spec.estimand_version
    assert summary["metadata"]["primary_backend"] == spec.primary_backend
    assert summary["metadata"]["backend_order"] == list(spec.backend_order)
    assert summary["metadata"]["signal_family_order"] == list(spec.signal_family_keys)
    assert summary["metadata"]["primary_rank_depth"] == spec.primary_rank_depth
    assert summary["metadata"]["confirmatory_rank_depths"] == list(spec.confirmatory_rank_depths)


def _assert_summary_top_20_contract(
    summary: dict[str, object],
    *,
    spec,
    keyword_count: int,
    actionable: bool,
    bh_applies: bool,
) -> dict[str, object]:
    top_20 = summary["rank_depths"]["top_20"]
    assert top_20["rank_depth_key"] == "top_20"
    assert top_20["max_serp_rank"] == spec.rank_depth_limit("top_20")
    assert top_20["analysis_mart_rows"] == keyword_count * 20
    assert top_20["panel_rows"] == keyword_count * 20
    assert top_20["keyword_count"] == keyword_count
    assert top_20["inference_mode"] == ("confirmatory" if keyword_count >= 10 else "underpowered")
    assert top_20["hard_fail"] is False
    assert top_20["actionable_association"] is actionable
    assert summary["actionable_association"] is actionable
    assert summary["actionable_association_by_rank_depth"]["top_20"] is actionable
    assert list(top_20["families"]) == list(spec.signal_family_keys)

    bge_spearman = top_20["spearman"]["backends"]["bge"]
    if bh_applies:
        assert bge_spearman["bh_q_values"] == [0.0] * keyword_count
        assert "bh_skipped_reason" not in bge_spearman
    else:
        assert bge_spearman["bh_skipped_reason"] == "underpowered"
        assert "bh_q_values" not in bge_spearman

    bge_regression = top_20["regression"]["backends"]["bge"]
    assert bge_regression["feature_model"]["covariance"]["clusters"] == ["target_keyword_id"]
    assert bge_regression["feature_model"]["covariance"]["type"] == "cluster"
    assert "naive_standard_error" not in bge_regression["feature_model"]
    assert bge_regression["feature_model"]["clustered_confidence_interval"][0] > 0
    assert bge_regression["feature_model"]["clustered_standard_error"] > 0
    assert top_20["spearman"]["backends"]["bge"]["median_rho"] == -1.0
    assert top_20["spearman"]["backends"]["bge"]["rho_iqr"] == 0.0
    assert top_20["spearman"]["backends"]["bge"]["fraction_same_sign"] == 1.0
    assert summary["spearman"] == top_20["spearman"]
    assert summary["regression"] == top_20["regression"]
    assert summary["plackett_luce"] == top_20["plackett_luce"]
    return top_20


def test_confirmatory_golden_fixture_pins_summary_and_diagnostics_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spec = load_analysis_spec()
    result, summary, diagnostics, report = _run_phase5_stats(
        tmp_path,
        _analysis_mart_frame(mode="confirmatory"),
        monkeypatch,
    )

    assert result.hard_fail is False
    _assert_contract_metadata(summary, spec)
    top_20 = _assert_summary_top_20_contract(
        summary,
        spec=spec,
        keyword_count=10,
        actionable=True,
        bh_applies=True,
    )

    assert top_20["regression"]["backends"]["bge"]["feature_model"]["coefficient"] == pytest.approx(0.25)
    assert top_20["regression"]["backends"]["gemini_doc_retrieval"]["feature_model"]["coefficient"] > top_20["regression"]["backends"]["bge"]["feature_model"]["coefficient"]
    assert top_20["regression"]["backends"]["gemini_semantic_similarity"]["feature_model"]["coefficient"] > top_20["regression"]["backends"]["gemini_doc_retrieval"]["feature_model"]["coefficient"]
    assert "### Robustness" in report
    assert "### Influence robustness" in report

    assert diagnostics is not None
    assert diagnostics["analysis_spec_version"] == spec.version
    assert diagnostics["metadata"]["signal_family_order"] == list(spec.signal_family_keys)
    assert diagnostics["rank_depths"]["top_20"]["multivariate_sensitivity"]["status"] in {
        "computed",
        "unresolved",
    }
    bge_diagnostics = diagnostics["rank_depths"]["top_20"]["regression"]["backends"]["bge"]
    assert bge_diagnostics["influence_sensitivity"]["status"] == "computed"
    assert bge_diagnostics["influence_sensitivity"]["coefficient_delta"] == pytest.approx(0.0)


def test_golden_fixture_boundaries_cover_bh_hard_fail_low_signal_influence_and_vif(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spec = load_analysis_spec()

    _, summary_10, diagnostics_10, _ = _run_phase5_stats(
        tmp_path / "k10",
        _analysis_mart_frame(mode="confirmatory", keyword_count=10),
        monkeypatch,
    )
    _, summary_9, _, _ = _run_phase5_stats(
        tmp_path / "k9",
        _analysis_mart_frame(mode="confirmatory", keyword_count=9),
        monkeypatch,
    )
    _, summary_low, diagnostics_low, _ = _run_phase5_stats(
        tmp_path / "low",
        _analysis_mart_frame(mode="low_signal"),
        monkeypatch,
    )
    _, summary_hard_fail, diagnostics_hard_fail, report_hard_fail = _run_phase5_stats(
        tmp_path / "hard",
        _analysis_mart_frame(mode="hard_fail"),
        monkeypatch,
    )
    _, summary_influential, diagnostics_influential, _ = _run_phase5_stats(
        tmp_path / "influential",
        _analysis_mart_frame(mode="confirmatory", influential=True),
        monkeypatch,
    )
    _, summary_collinear, diagnostics_collinear, _ = _run_phase5_stats(
        tmp_path / "collinear",
        _analysis_mart_frame(mode="collinear"),
        monkeypatch,
    )
    _, summary_single_keyword, diagnostics_single_keyword, _ = _run_phase5_stats(
        tmp_path / "single",
        _analysis_mart_frame(mode="confirmatory", keyword_count=1),
        monkeypatch,
    )

    _assert_contract_metadata(summary_10, spec)
    _assert_summary_top_20_contract(
        summary_10,
        spec=spec,
        keyword_count=10,
        actionable=True,
        bh_applies=True,
    )

    assert summary_9["rank_depths"]["top_20"]["spearman"]["backends"]["bge"]["bh_skipped_reason"] == "underpowered"
    assert "bh_q_values" not in summary_9["rank_depths"]["top_20"]["spearman"]["backends"]["bge"]

    assert summary_low["actionable_association"] is False
    assert summary_low["rank_depths"]["top_20"]["actionable_association"] is False
    assert summary_low["rank_depths"]["top_20"]["spearman"]["backends"]["bge"]["median_rho"] != -1.0
    assert summary_low["rank_depths"]["top_20"]["regression"]["backends"]["bge"]["feature_model"]["clustered_confidence_interval"][0] < 0
    assert diagnostics_low is not None
    assert diagnostics_low["rank_depths"]["top_20"]["regression"]["backends"]["bge"]["influence_sensitivity"]["coefficient_delta"] != 0.0

    assert summary_hard_fail["hard_fail"] is True
    assert summary_hard_fail["rank_depths"]["top_20"]["hard_fail"] is True
    assert summary_hard_fail["rank_depths"]["top_20"]["actionable_association"] is False
    assert "spearman" not in summary_hard_fail
    assert "regression" not in summary_hard_fail
    assert diagnostics_hard_fail is None
    assert "Confirmatory inference skipped because hard-fail guardrails did not pass." in report_hard_fail

    assert diagnostics_influential is not None
    influential_delta = diagnostics_influential["rank_depths"]["top_20"]["regression"]["backends"]["bge"][
        "influence_sensitivity"
    ]["coefficient_delta"]
    assert influential_delta != 0.0
    assert diagnostics_influential["rank_depths"]["top_20"]["regression"]["backends"]["bge"][
        "influence_sensitivity"
    ]["status"] == "computed"

    assert diagnostics_collinear is not None
    multivariate = diagnostics_collinear["rank_depths"]["top_20"]["multivariate_sensitivity"]
    assert multivariate["status"] in {"computed", "unresolved"}
    assert multivariate["drop_log"][0]["dropped_backend"] == "gemini_semantic_similarity"
    assert multivariate["drop_log"][1]["dropped_backend"] == "gemini_doc_retrieval"
    assert multivariate["kept_backends"] == ["bge"]

    assert summary_single_keyword["rank_depths"]["top_20"]["keyword_count"] == 1
    assert summary_single_keyword["rank_depths"]["top_20"]["inference_mode"] == "underpowered"
    assert summary_single_keyword["rank_depths"]["top_20"]["spearman"]["backends"]["bge"][
        "bh_skipped_reason"
    ] == "underpowered"
    assert (
        summary_single_keyword["rank_depths"]["top_20"]["regression"]["backends"]["bge"][
            "feature_model"
        ]["covariance"]["type"]
        == "HC3"
    )
    assert summary_single_keyword["rank_depths"]["top_20"]["regression"]["backends"]["bge"][
        "feature_model"
    ]["covariance"]["clusters"] == []
    assert "naive_standard_error" not in summary_single_keyword["rank_depths"]["top_20"]["regression"]["backends"]["bge"]["feature_model"]
    assert diagnostics_single_keyword is not None
    assert diagnostics_single_keyword["rank_depths"]["top_20"]["regression"]["backends"]["bge"][
        "influence_sensitivity"
    ]["status"] == "computed"

