from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest
import yaml

from seo_rank.data.features import ONPAGE_FEATURES_EXTRA_COLUMNS
from seo_rank.stats.families import (
    load_signal_family_registry,
    plackett_luce_enabled_for_family,
)
from seo_rank.stats.spec import load_analysis_spec


ONPAGE_FAMILY_KEYS = (
    "onpage_content_quality",
    "onpage_core_web_vitals",
    "onpage_technical_checks",
)
ONPAGE_SIGNAL_COLUMNS = frozenset(ONPAGE_FEATURES_EXTRA_COLUMNS) - {"onpage_signal_id"}


ROOT = Path(__file__).resolve().parents[2]


def test_signal_family_registry_preserves_order_and_panel_grain() -> None:
    analysis_spec = load_analysis_spec()
    registry = analysis_spec.signal_families

    assert registry.panel_grain == (
        "target_keyword_id",
        "canonical_url_hash",
    )
    assert registry.keys == (
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
        *ONPAGE_FAMILY_KEYS,
    )
    assert registry.family("gemini_doc_retrieval").signal_columns == (
        "gemini_doc_retrieval_normalized_score",
    )
    assert registry.family("textrazor_entailment_score_prior_context").signal_columns == (
        "textrazor_entailment_score",
        "textrazor_entailment_prior",
        "textrazor_entailment_context",
    )
    assert registry.family("backlinks_counts").kind == "backlinks_metric"
    assert registry.family("backlinks_counts").signal_columns == (
        "backlinks_count",
        "referring_domains_count",
        "dofollow_backlinks_count",
    )
    assert registry.family("onpage_content_quality").kind == "onpage_metric"
    assert registry.family("onpage_content_quality").signal_columns == (
        "onpage_score",
        "plain_text_word_count",
        "plain_text_rate",
        "flesch_kincaid_readability_index",
        "coleman_liau_readability_index",
        "smog_readability_index",
        "dale_chall_readability_index",
    )
    assert registry.family("onpage_core_web_vitals").signal_columns == (
        "time_to_first_byte_ms",
        "largest_contentful_paint_ms",
        "cumulative_layout_shift",
        "total_transfer_size",
    )
    assert registry.family("onpage_technical_checks").signal_columns == (
        "title_too_long",
        "title_too_short",
        "no_title",
        "no_description",
        "no_h1_tag",
        "canonical",
        "is_https",
        "has_render_blocking_resources",
        "duplicate_meta_tags",
        "has_meta_title",
        "irrelevant_description",
        "low_readability_rate",
        "has_valid_structured_data",
        "micromarkup_items_count",
        "micromarkup_errors_count",
        "micromarkup_warnings_count",
    )
    assert registry.source_mart_for_family("onpage_content_quality") == "onpage_features"
    assert registry.families_by_kind("onpage_metric") == tuple(
        registry.family(key) for key in ONPAGE_FAMILY_KEYS
    )
    assert registry.families_by_kind("similarity")[0].key == "bge"


def test_onpage_metric_families_defer_family_plackett_luce() -> None:
    analysis_spec = load_analysis_spec()

    for family_key in ONPAGE_FAMILY_KEYS:
        family = analysis_spec.signal_families.family(family_key)
        assert family.kind == "onpage_metric"
        assert plackett_luce_enabled_for_family(family) is False

    assert plackett_luce_enabled_for_family(
        analysis_spec.signal_families.family("backlinks_counts")
    )
    assert plackett_luce_enabled_for_family(
        analysis_spec.signal_families.family("textrazor_topic_score")
    )


def test_onpage_signal_columns_cover_onpage_features_mart() -> None:
    analysis_spec = load_analysis_spec()
    registry = analysis_spec.signal_families

    registered_columns: set[str] = set()
    for key in ONPAGE_FAMILY_KEYS:
        registered_columns.update(registry.family(key).signal_columns)

    assert registered_columns == set(ONPAGE_SIGNAL_COLUMNS)


@pytest.mark.parametrize(
    "mutator, expected_message",
    [
        (lambda families: families[0].pop("signal_columns"), "signal_columns"),
        (lambda families: families.__setitem__(1, deepcopy(families[0])), "duplicate"),
    ],
)
def test_load_signal_family_registry_rejects_malformed_entries(
    tmp_path: Path,
    mutator,
    expected_message: str,
) -> None:
    spec_data = yaml.safe_load((ROOT / "analysis_spec.v1.yaml").read_text(encoding="utf-8"))
    families = spec_data["signal_families"]["families"]
    mutator(families)

    with pytest.raises(ValueError, match=expected_message):
        load_signal_family_registry(
            panel_grain=("target_keyword_id", "canonical_url_hash"),
            raw_spec=spec_data["signal_families"],
        )


def test_load_signal_family_registry_rejects_duplicate_signal_columns_across_families() -> None:
    spec_data = yaml.safe_load((ROOT / "analysis_spec.v1.yaml").read_text(encoding="utf-8"))
    families = spec_data["signal_families"]["families"]
    families[4]["signal_columns"].append("bge_normalized_score")

    with pytest.raises(ValueError, match="duplicate signal column"):
        load_signal_family_registry(
            panel_grain=("target_keyword_id", "canonical_url_hash"),
            raw_spec=spec_data["signal_families"],
        )
