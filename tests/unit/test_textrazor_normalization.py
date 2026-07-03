import json

import polars as pl

from seo_rank.data.normalize import build_textrazor_page_metrics_frame, stable_id
from seo_rank.textrazor import fixture_entity_response, fixture_page_metrics_response, normalize_entities


def test_normalize_entities_preserves_textrazor_schema_for_page_text() -> None:
    response = fixture_entity_response(
        url="https://example.com/technical-seo/1",
        text="Technical SEO helps crawlers discover important pages.",
    )

    entities = normalize_entities(
        response,
        url="https://example.com/technical-seo/1",
    )

    assert entities == [
        {
            "url": "https://example.com/technical-seo/1",
            "entity_id": "technical-seo",
            "matched_text": "Technical SEO",
            "confidence": 7.5,
            "relevance": 0.92,
            "types": ["Topic", "SEO"],
        },
        {
            "url": "https://example.com/technical-seo/1",
            "entity_id": "crawler",
            "matched_text": "crawlers",
            "confidence": 5.5,
            "relevance": 0.71,
            "types": ["SoftwareAgent"],
        },
    ]


def test_build_textrazor_page_metrics_frame_materializes_page_level_signals() -> None:
    response = fixture_page_metrics_response(
        url="https://example.com/technical-seo/1",
        text="Technical SEO helps crawlers discover important pages.",
    )
    frame = pl.DataFrame(
        [
            {
                "run_id": "run-1",
                "response_id": "page-resp-1",
                "target_keyword": "Technical SEO",
                "response_body_bytes": json.dumps(response).encode("utf-8"),
            }
        ]
    )

    metrics = build_textrazor_page_metrics_frame(frame, run_id="run-1")

    assert metrics.to_dicts() == [
        {
            "run_id": "run-1",
            "target_keyword_id": stable_id("Technical SEO"),
            "target_keyword": "Technical SEO",
            "response_id": "page-resp-1",
            "canonical_url_hash": stable_id("https://example.com/technical-seo/1"),
            "url": "https://example.com/technical-seo/1",
            "page_metrics_row_id": stable_id(
                "run-1",
                "Technical SEO",
                "https://example.com/technical-seo/1",
            ),
            "textrazor_entity_confidence_score": 7.5,
            "textrazor_entity_relevance_score": 0.92,
            "textrazor_topic_score": 0.66,
            "textrazor_category_score": 0.83,
            "textrazor_classifier_score": 0.74,
            "textrazor_entailment_score": 0.61,
            "textrazor_entailment_prior": 0.34,
            "textrazor_entailment_context": 0.27,
            "textrazor_word_count": 2,
            "textrazor_grammar_count": 1,
            "textrazor_sense_count": 1,
            "textrazor_spelling_count": 1,
            "textrazor_relation_count": 2,
            "textrazor_property_count": 1,
            "textrazor_noun_phrase_count": 3,
            "textrazor_entities_present": True,
            "textrazor_topics_present": True,
            "textrazor_categories_present": True,
            "textrazor_entailments_present": True,
            "textrazor_words_present": True,
            "textrazor_relations_present": True,
            "textrazor_properties_present": True,
            "textrazor_noun_phrases_present": True,
            "textrazor_page_metrics_complete": True,
            "schema_version": "curated.v1",
        }
    ]


def test_build_textrazor_page_metrics_frame_falls_back_to_category_score_when_classifier_score_missing() -> None:
    response = fixture_page_metrics_response(
        url="https://example.com/technical-seo/1",
        text="Technical SEO helps crawlers discover important pages.",
    )
    response["response"]["categories"][0].pop("classifierScore")
    frame = pl.DataFrame(
        [
            {
                "run_id": "run-1",
                "response_id": "page-resp-1",
                "target_keyword": "Technical SEO",
                "response_body_bytes": json.dumps(response).encode("utf-8"),
            }
        ]
    )

    metrics = build_textrazor_page_metrics_frame(frame, run_id="run-1")

    assert metrics.to_dicts() == [
        {
            "run_id": "run-1",
            "target_keyword_id": stable_id("Technical SEO"),
            "target_keyword": "Technical SEO",
            "response_id": "page-resp-1",
            "canonical_url_hash": stable_id("https://example.com/technical-seo/1"),
            "url": "https://example.com/technical-seo/1",
            "page_metrics_row_id": stable_id(
                "run-1",
                "Technical SEO",
                "https://example.com/technical-seo/1",
            ),
            "textrazor_entity_confidence_score": 7.5,
            "textrazor_entity_relevance_score": 0.92,
            "textrazor_topic_score": 0.66,
            "textrazor_category_score": 0.83,
            "textrazor_classifier_score": 0.83,
            "textrazor_entailment_score": 0.61,
            "textrazor_entailment_prior": 0.34,
            "textrazor_entailment_context": 0.27,
            "textrazor_word_count": 2,
            "textrazor_grammar_count": 1,
            "textrazor_sense_count": 1,
            "textrazor_spelling_count": 1,
            "textrazor_relation_count": 2,
            "textrazor_property_count": 1,
            "textrazor_noun_phrase_count": 3,
            "textrazor_entities_present": True,
            "textrazor_topics_present": True,
            "textrazor_categories_present": True,
            "textrazor_entailments_present": True,
            "textrazor_words_present": True,
            "textrazor_relations_present": True,
            "textrazor_properties_present": True,
            "textrazor_noun_phrases_present": True,
            "textrazor_page_metrics_complete": True,
            "schema_version": "curated.v1",
        }
    ]


def test_build_textrazor_page_metrics_frame_marks_missing_sections_incomplete() -> None:
    response = fixture_page_metrics_response(
        url="https://example.com/technical-seo/1",
        text="Technical SEO helps crawlers discover important pages.",
    )
    response["response"].pop("topics")
    response["response"].pop("categories")
    response["response"].pop("entailments")
    response["response"].pop("words")
    response["response"].pop("relations")
    response["response"].pop("properties")
    response["response"].pop("nounPhrases")
    frame = pl.DataFrame(
        [
            {
                "run_id": "run-1",
                "response_id": "page-resp-1",
                "target_keyword": "Technical SEO",
                "response_body_bytes": json.dumps(response).encode("utf-8"),
            }
        ]
    )

    metrics = build_textrazor_page_metrics_frame(frame, run_id="run-1")

    assert metrics.to_dicts() == [
        {
            "run_id": "run-1",
            "target_keyword_id": stable_id("Technical SEO"),
            "target_keyword": "Technical SEO",
            "response_id": "page-resp-1",
            "canonical_url_hash": stable_id("https://example.com/technical-seo/1"),
            "url": "https://example.com/technical-seo/1",
            "page_metrics_row_id": stable_id(
                "run-1",
                "Technical SEO",
                "https://example.com/technical-seo/1",
            ),
            "textrazor_entity_confidence_score": 7.5,
            "textrazor_entity_relevance_score": 0.92,
            "textrazor_topic_score": None,
            "textrazor_category_score": None,
            "textrazor_classifier_score": None,
            "textrazor_entailment_score": None,
            "textrazor_entailment_prior": None,
            "textrazor_entailment_context": None,
            "textrazor_word_count": None,
            "textrazor_grammar_count": None,
            "textrazor_sense_count": None,
            "textrazor_spelling_count": None,
            "textrazor_relation_count": None,
            "textrazor_property_count": None,
            "textrazor_noun_phrase_count": None,
            "textrazor_entities_present": True,
            "textrazor_topics_present": False,
            "textrazor_categories_present": False,
            "textrazor_entailments_present": False,
            "textrazor_words_present": False,
            "textrazor_relations_present": False,
            "textrazor_properties_present": False,
            "textrazor_noun_phrases_present": False,
            "textrazor_page_metrics_complete": False,
            "schema_version": "curated.v1",
        }
    ]
