from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest
import yaml

from seo_rank.stats.families import load_signal_family_registry
from seo_rank.stats.spec import load_analysis_spec


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
    )
    assert registry.family("gemini_doc_retrieval").signal_columns == (
        "gemini_doc_retrieval_normalized_score",
    )
    assert registry.family("textrazor_entailment_score_prior_context").signal_columns == (
        "textrazor_entailment_score",
        "textrazor_entailment_prior",
        "textrazor_entailment_context",
    )
    assert registry.families_by_kind("similarity")[0].key == "bge"


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
