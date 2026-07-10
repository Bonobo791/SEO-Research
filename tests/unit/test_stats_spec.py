import logging
from pathlib import Path

import pytest

import seo_rank.stats as stats
from seo_rank.stats import artifacts
from seo_rank.stats.spec import load_analysis_spec


def test_stats_package_exports_module_surface() -> None:
    assert stats.spec.__name__ == "seo_rank.stats.spec"
    assert stats.panel.__name__ == "seo_rank.stats.panel"
    assert stats.spearman.__name__ == "seo_rank.stats.spearman"
    assert stats.plackett_luce.__name__ == "seo_rank.stats.plackett_luce"
    assert stats.rank_depth.__name__ == "seo_rank.stats.rank_depth"
    assert stats.regression.__name__ == "seo_rank.stats.regression"
    assert stats.diagnostics.__name__ == "seo_rank.stats.diagnostics"
    assert stats.bh.__name__ == "seo_rank.stats.bh"
    assert stats.families.__name__ == "seo_rank.stats.families"
    assert stats.artifacts.__name__ == "seo_rank.stats.artifacts"


def test_load_analysis_spec_reads_repo_root_yaml() -> None:
    analysis_spec = load_analysis_spec()

    assert analysis_spec.path == Path("analysis_spec.v1.1.yaml")
    assert analysis_spec.version == "v1.1"
    assert analysis_spec.estimand_version == "v1.1"
    assert analysis_spec.primary_backend == "bge"
    assert analysis_spec.backend_order == (
        "bge",
        "gemini_doc_retrieval",
        "gemini_semantic_similarity",
    )
    assert analysis_spec.panel_grain == (
        "target_keyword_id",
        "canonical_url_hash",
    )
    assert analysis_spec.signal_family_keys == (
        "bge",
        "gemini_doc_retrieval",
        "gemini_semantic_similarity",
        "textrazor_entity_confidence_relevance",
        "textrazor_topic_score",
        "textrazor_category_classifier_score",
        "textrazor_entailment_score_prior_context",
        "textrazor_word_grammar_sense_spelling",
        "textrazor_relation_property_noun_phrase",
        "backlinks_counts",
        "onpage_content_quality",
        "onpage_core_web_vitals",
        "onpage_technical_checks",
    )
    assert analysis_spec.estimand["outcome"] == "-log(serp_rank)"


def test_load_analysis_spec_includes_plackett_luce_secondary_estimand() -> None:
    analysis_spec = load_analysis_spec()
    plackett_luce = analysis_spec.estimand["plackett_luce"]

    assert plackett_luce["outcome"] == "rank_ordered_logit"
    assert plackett_luce["formula"] == "log(observed_variable + 1) + site_scale"
    assert plackett_luce["clustered_se"] == "target_keyword_id"
    assert plackett_luce["choice_set_scope"] == "observed_top_20_serp_results_per_keyword"
    assert plackett_luce["iia_sensitivity"] == {
        "leave_one_out_top_rank": True,
    }


def test_load_analysis_spec_exposes_signal_family_metadata() -> None:
    analysis_spec = load_analysis_spec()

    assert analysis_spec.signal_family("bge").kind == "similarity"
    assert analysis_spec.signal_family("bge").signal_columns == ("bge_normalized_score",)
    assert analysis_spec.signal_family("textrazor_topic_score").kind == "textrazor_scalar"
    assert analysis_spec.signal_family("textrazor_topic_score").signal_columns == (
        "textrazor_topic_score",
    )
    assert analysis_spec.signal_family("textrazor_word_grammar_sense_spelling").kind == "textrazor_structural"
    assert analysis_spec.signal_family("backlinks_counts").kind == "backlinks_metric"
    assert analysis_spec.signal_family("backlinks_counts").signal_columns == (
        "backlinks_count",
        "referring_domains_count",
        "dofollow_backlinks_count",
    )
    assert analysis_spec.signal_family("onpage_content_quality").kind == "onpage_metric"
    assert analysis_spec.signal_family("onpage_core_web_vitals").kind == "onpage_metric"
    assert analysis_spec.signal_family("onpage_technical_checks").kind == "onpage_metric"
    assert analysis_spec.signal_families.similarity_keys == (
        "bge",
        "gemini_doc_retrieval",
        "gemini_semantic_similarity",
    )


def test_load_analysis_spec_exposes_multivariate_sensitivity_settings() -> None:
    analysis_spec = load_analysis_spec()

    assert analysis_spec.multivariate_vif_threshold == 5


def test_load_analysis_spec_declares_missing_control_policy() -> None:
    analysis_spec = load_analysis_spec()

    assert analysis_spec.data["estimand"]["missing_control_policy"] == "complete_case"
    assert analysis_spec.backend_drop_order == (
        "gemini_semantic_similarity",
        "gemini_doc_retrieval",
        "bge",
    )


def test_v1_spec_remains_loadable_for_historical_runs() -> None:
    analysis_spec = load_analysis_spec("analysis_spec.v1.yaml")

    assert analysis_spec.version == "v1"
    assert "deprecated_html_tags" in analysis_spec.estimand["baseline_model"]


def test_load_analysis_spec_logs_version_and_rank_depths(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="seo_rank.stats.spec")

    load_analysis_spec()

    messages = [record.getMessage() for record in caplog.records]
    assert any("loaded analysis spec version=v1" in message for message in messages)
    assert any("primary_rank_depth=top_20" in message for message in messages)


def test_build_stats_output_metadata_exposes_estimand_version() -> None:
    analysis_spec = load_analysis_spec()
    metadata = artifacts.build_stats_output_metadata(analysis_spec)

    assert metadata == {
        "analysis_spec_version": "v1.1",
        "estimand_version": "v1.1",
        "primary_backend": "bge",
        "backend_order": [
            "bge",
            "gemini_doc_retrieval",
            "gemini_semantic_similarity",
        ],
        "signal_family_order": [
            "bge",
            "gemini_doc_retrieval",
            "gemini_semantic_similarity",
        "textrazor_entity_confidence_relevance",
        "textrazor_topic_score",
        "textrazor_category_classifier_score",
        "textrazor_entailment_score_prior_context",
        "textrazor_word_grammar_sense_spelling",
        "textrazor_relation_property_noun_phrase",
        "backlinks_counts",
        "onpage_content_quality",
        "onpage_core_web_vitals",
        "onpage_technical_checks",
    ],
        "primary_rank_depth": "top_20",
        "confirmatory_rank_depths": ["top_20", "top_10", "top_5", "top_3"],
    }
