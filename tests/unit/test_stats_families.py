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
TEXTRAZOR_PHASE57_FAMILY_KEYS = (
    "textrazor_entity_salience",
    "textrazor_entity_coverage",
    "textrazor_entity_linkage",
    "textrazor_syntactic_complexity",
)
EXCLUDED_MODEL_COLUMNS = frozenset(
    {
        "is_4xx_code",
        "is_5xx_code",
        "is_broken",
        "broken_links",
        "broken_resources",
        "resource_errors_count",
        "no_title",
        "no_description",
        "no_h1_tag",
        "duplicate_title_tag",
        "duplicate_title",
        "duplicate_description",
        "duplicate_meta_tags",
        "irrelevant_title",
        "irrelevant_description",
        "irrelevant_meta_keywords",
        "no_encoding_meta_tag",
        "no_content_encoding",
        "https_to_http_links",
        "no_doctype",
        "deprecated_html_tags",
        "has_meta_refresh_redirect",
        "no_image_alt",
        "high_loading_time",
        "high_waiting_time",
        "low_readability_rate",
        "low_content_rate",
        "is_www",
        "has_html_doctype",
        "meta_charset_consistency",
        "from_sitemap",
        "canonical",
        "is_https",
        "has_meta_title",
        "title_too_long",
        "title_too_short",
        "large_page_size",
        "size_greater_than_3mb",
        "has_render_blocking_resources",
        "render_blocking_scripts_count",
        "render_blocking_stylesheets_count",
        "scripts_size",
        "stylesheets_size",
        "total_transfer_size",
        "total_dom_size",
        "cumulative_layout_shift",
        "largest_contentful_paint_ms",
        "time_to_first_byte_ms",
        "first_input_delay_ms",
    }
)
ONPAGE_SIGNAL_COLUMNS = (
    frozenset(ONPAGE_FEATURES_EXTRA_COLUMNS)
    - {"onpage_signal_id"}
    | {"deprecated_html_tags", "meta_keywords_to_content_consistency", "time_to_first_byte_ms"}
)
ONPAGE_CONTENT_QUALITY_COLUMNS = (
    "onpage_score",
    "plain_text_word_count",
    "plain_text_rate",
    "flesch_kincaid_readability_index",
    "coleman_liau_readability_index",
    "smog_readability_index",
    "dale_chall_readability_index",
    "description_to_content_consistency",
    "title_to_content_consistency",
    "meta_keywords_to_content_consistency",
)
ONPAGE_CORE_WEB_VITALS_COLUMNS = (
    "connection_time_ms",
    "time_to_secure_connection_ms",
    "request_sent_time_ms",
    "download_time_ms",
    "duration_time_ms",
    "fetch_end_ms",
    "dom_complete_ms",
    "time_to_interactive_ms",
)
ONPAGE_TECHNICAL_CHECKS_COLUMNS = (
    "has_valid_structured_data",
    "micromarkup_items_count",
    "micromarkup_errors_count",
    "micromarkup_warnings_count",
    "is_redirect",
    "high_content_rate",
    "high_character_count",
    "small_page_size",
    "no_image_title",
    "no_favicon",
    "seo_friendly_url",
    "flash",
    "frame",
    "lorem_ipsum",
    "has_micromarkup",
    "has_micromarkup_errors",
    "description_length",
    "title_length",
    "external_links_count",
    "internal_links_count",
    "images_count",
    "images_size",
    "scripts_count",
    "stylesheets_count",
    "follow",
    "inbound_links_count",
    "duplicate_meta_tags_count",
    "h1_count",
    "h2_count",
    "h3_count",
    "has_og_tags",
    "has_twitter_tags",
    "cache_control_cachable",
    "cache_control_ttl",
    "resource_warnings_count",
    "duplicate_content",
    "click_depth",
    "encoded_size",
)


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
        "textrazor_word_sense_spelling",
        "textrazor_relation_property_noun_phrase",
        *TEXTRAZOR_PHASE57_FAMILY_KEYS,
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
    assert registry.family("onpage_content_quality").signal_columns == ONPAGE_CONTENT_QUALITY_COLUMNS
    assert registry.family("onpage_core_web_vitals").signal_columns == ONPAGE_CORE_WEB_VITALS_COLUMNS
    assert registry.family("onpage_technical_checks").signal_columns == ONPAGE_TECHNICAL_CHECKS_COLUMNS
    assert registry.source_mart_for_family("onpage_content_quality") == "onpage_features"
    assert registry.family("textrazor_entity_salience").signal_columns == (
        "textrazor_entity_salience_mean",
        "textrazor_entity_salience_median",
        "textrazor_entity_salience_top3_max",
        "textrazor_entity_salience_mention_weighted",
        "textrazor_salience_unique_entity_count",
    )
    assert registry.family("textrazor_entity_coverage").signal_columns == (
        "textrazor_entity_mention_count",
        "textrazor_unique_entity_count",
        "textrazor_unique_entity_density_per_1k_words",
        "textrazor_entity_mention_density_per_1k_words",
    )
    assert registry.family("textrazor_entity_linkage").signal_columns == (
        "textrazor_linked_entity_fraction",
        "textrazor_entity_type_entropy",
    )
    assert registry.family("textrazor_syntactic_complexity").signal_columns == (
        "textrazor_dependency_depth_mean",
        "textrazor_dependency_relation_type_count",
        "textrazor_part_of_speech_type_count",
    )
    for family_key in TEXTRAZOR_PHASE57_FAMILY_KEYS:
        family = registry.family(family_key)
        assert registry.source_mart_for_family(family_key) == "textrazor_page_metrics"
        assert plackett_luce_enabled_for_family(family) is True
    assert registry.families_by_kind("onpage_metric") == tuple(
        registry.family(key) for key in ONPAGE_FAMILY_KEYS
    )
    assert registry.families_by_kind("similarity")[0].key == "bge"


def test_onpage_metric_families_enable_family_plackett_luce() -> None:
    analysis_spec = load_analysis_spec()

    for family_key in ONPAGE_FAMILY_KEYS:
        family = analysis_spec.signal_families.family(family_key)
        assert family.kind == "onpage_metric"
        assert plackett_luce_enabled_for_family(family) is True

    assert plackett_luce_enabled_for_family(
        analysis_spec.signal_families.family("backlinks_counts")
    )
    assert plackett_luce_enabled_for_family(
        analysis_spec.signal_families.family("textrazor_topic_score")
    )


def test_onpage_signal_columns_cover_model_eligible_onpage_features() -> None:
    analysis_spec = load_analysis_spec()
    registry = analysis_spec.signal_families

    registered_columns: set[str] = set()
    for key in ONPAGE_FAMILY_KEYS:
        registered_columns.update(registry.family(key).signal_columns)

    assert registered_columns == set(ONPAGE_SIGNAL_COLUMNS) - EXCLUDED_MODEL_COLUMNS


def test_excluded_onpage_columns_are_not_registered_for_models() -> None:
    registry = load_analysis_spec().signal_families
    model_columns = {
        column
        for family in registry.families
        for column in family.signal_columns
    }

    assert not model_columns & EXCLUDED_MODEL_COLUMNS


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
