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
import json


import polars as pl

from seo_rank.data.features import FEATURE_VALIDATION_RULES
from seo_rank.data.normalize import (
    CURATED_VALIDATION_RULES,
    build_textrazor_page_metrics_frame,
    stable_id,
)
from seo_rank.textrazor import (
    build_entity_request,
    fixture_entity_response,
    fixture_page_metrics_response,
    normalize_entities,
    normalize_page_metrics,
)


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
            "entity_english_id": None,
            "matched_text": "Technical SEO",
            "confidence": 7.5,
            "relevance": 0.92,
            "types": ["Topic", "SEO"],
            "wikidata_id": None,
            "wiki_link": None,
            "freebase_types": [],
            "enriched_data_keys": [],
        },
        {
            "url": "https://example.com/technical-seo/1",
            "entity_id": "crawler",
            "entity_english_id": None,
            "matched_text": "crawlers",
            "confidence": 5.5,
            "relevance": 0.71,
            "types": ["SoftwareAgent"],
            "wikidata_id": None,
            "wiki_link": None,
            "freebase_types": [],
            "enriched_data_keys": [],
        },
    ]


def test_normalize_entities_retains_kb_linkage_metadata() -> None:
    response = fixture_entity_response(
        url="https://example.com/technical-seo/1",
        text="Technical SEO helps crawlers discover important pages.",
    )
    response["response"]["entities"][0].update(
        {
            "entityEnglishId": "technical-seo",
            "wikidataId": "Q180711",
            "wikiLink": "https://en.wikipedia.org/wiki/Search_engine_optimization",
            "freebaseTypes": ["/internet/website", 7, ""],
            "data": {"zeta": {"ignored": True}, "alpha": "value", "beta": 2, "gamma": 3},
        }
    )

    entity = normalize_entities(response, url="https://example.com/technical-seo/1")[0]

    assert entity["entity_english_id"] == "technical-seo"
    assert entity["wikidata_id"] == "Q180711"
    assert entity["wiki_link"] == "https://en.wikipedia.org/wiki/Search_engine_optimization"
    assert entity["freebase_types"] == ["/internet/website"]
    assert entity["enriched_data_keys"] == ["alpha", "beta", "gamma"]


def test_normalize_page_metrics_keeps_top_topic_and_category_identity() -> None:
    response = fixture_page_metrics_response(
        url="https://example.com/technical-seo/1",
        text="Technical SEO helps crawlers discover important pages.",
    )
    response["response"]["topics"] = [
        {"label": "First tie", "score": 0.91},
        {"label": "Second tie", "score": 0.91},
        {"label": "Ignored malformed", "score": "0.99"},
    ]
    response["response"]["categories"] = [
        {
            "label": "Media topic",
            "score": 0.84,
            "classifierId": "textrazor_mediatopics_2023Q1",
        },
        {
            "label": "IAB topic",
            "score": 0.96,
            "classifierId": "textrazor_iab_content_taxonomy_3.0",
        },
    ]

    metrics = normalize_page_metrics(response, url="https://example.com/technical-seo/1")

    assert metrics["textrazor_top_topic_label"] == "First tie"
    assert metrics["textrazor_top_topic_score"] == 0.91
    assert metrics["textrazor_top_category_label"] == "IAB topic"
    assert (
        metrics["textrazor_top_category_classifier_id"]
        == "textrazor_iab_content_taxonomy_3.0"
    )


def test_build_entity_request_requests_media_topics_and_iab_taxonomy() -> None:
    request = build_entity_request({"text": "Example text"})

    assert request.body["classifiers"] == (
        "textrazor_mediatopics_2023Q1,textrazor_iab_content_taxonomy_3.0"
    )


def test_top_topic_score_is_bounded_in_curated_and_feature_contracts() -> None:
    assert CURATED_VALIDATION_RULES["textrazor_page_metrics_curated"]["bounded_columns"][
        "textrazor_top_topic_score"
    ] == (0, 1)
    assert FEATURE_VALIDATION_RULES["textrazor_page_metrics"]["bounded_columns"][
        "textrazor_top_topic_score"
    ] == (0, 1)


def test_normalize_page_metrics_materializes_structured_text_features() -> None:
    response = fixture_page_metrics_response(
        url="https://example.com/technical-seo/1",
        text="Technical SEO helps crawlers discover pages.",
    )
    response["response"]["sentences"] = [
        {
            "words": [
                {"token": "Technical"},
                {"token": "SEO"},
                {"token": "helps"},
                {"token": "crawlers"},
                {"token": "discover"},
                {"token": "pages"},
            ]
        }
    ]
    response["response"]["nounPhrases"] = [
        {"wordPositions": [0, 1]},
        {"wordPositions": [3, 5]},
        {"wordPositions": [99]},
        {"wordPositions": [0, 1]},
    ]
    response["response"]["relations"] = [
        {
            "relation": "improves",
            "params": [
                {"name": "SUBJECT", "wordPositions": [0, 1]},
                {"name": "OBJECT", "wordPositions": [3, 5]},
            ],
        },
        {
            "relation": "describes",
            "params": [{"name": "OBJECT", "wordPositions": "invalid"}],
        },
    ]
    response["response"]["properties"] = [
        {"name": "crawlability"},
        {"name": "indexability"},
        {"name": "crawlability"},
        {"name": "performance"},
    ]

    metrics = normalize_page_metrics(response, url="https://example.com/technical-seo/1")

    assert metrics["textrazor_top_noun_phrase_texts"] == [
        "Technical SEO",
        "crawlers pages",
    ]
    assert metrics["textrazor_relation_predicate_labels"] == ["improves", "describes"]
    assert metrics["textrazor_relation_param_labels"] == [
        "SUBJECT: Technical SEO",
        "OBJECT: crawlers pages",
    ]
    assert metrics["textrazor_property_names"] == [
        "crawlability",
        "indexability",
        "performance",
    ]
    assert metrics["textrazor_entailment_prior"] == 0.34
    assert metrics["textrazor_entailment_context"] == 0.27


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
            "textrazor_top_topic_label": "Technical SEO",
            "textrazor_top_topic_score": 0.66,
            "textrazor_category_score": 0.83,
            "textrazor_classifier_score": 0.74,
            "textrazor_top_category_label": "Search engine optimization",
            "textrazor_top_category_classifier_id": "textrazor_mediatopics_2023Q1",
            "textrazor_entailment_score": 0.61,
            "textrazor_entailment_prior": 0.34,
            "textrazor_entailment_context": 0.27,
            "textrazor_word_count": 2,
            "textrazor_sense_score": 0.91,
            "textrazor_spelling_suggestion_count": 1,
            "textrazor_relation_count": 2,
            "textrazor_property_count": 1,
            "textrazor_noun_phrase_count": 3,
            "textrazor_top_noun_phrase_texts": [],
            "textrazor_relation_predicate_labels": [],
            "textrazor_relation_param_labels": [],
            "textrazor_property_names": ["crawlability"],
            "textrazor_dependency_depth_mean": 0.5,
            "textrazor_dependency_relation_type_count": 2,
            "textrazor_part_of_speech_type_count": 2,
            "textrazor_entity_mention_count": 2,
            "textrazor_unique_entity_count": 2,
            "textrazor_unique_entity_density_per_1k_words": 1000.0,
            "textrazor_entity_mention_density_per_1k_words": 1000.0,
            "textrazor_entities_present": True,
            "textrazor_topics_present": True,
            "textrazor_categories_present": True,
            "textrazor_entailments_present": True,
            "textrazor_words_present": True,
            "textrazor_relations_present": True,
            "textrazor_properties_present": True,
            "textrazor_noun_phrases_present": True,
            "textrazor_dependency_trees_present": True,
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
            "textrazor_top_topic_label": "Technical SEO",
            "textrazor_top_topic_score": 0.66,
            "textrazor_category_score": 0.83,
            "textrazor_classifier_score": 0.83,
            "textrazor_top_category_label": "Search engine optimization",
            "textrazor_top_category_classifier_id": "textrazor_mediatopics_2023Q1",
            "textrazor_entailment_score": 0.61,
            "textrazor_entailment_prior": 0.34,
            "textrazor_entailment_context": 0.27,
            "textrazor_word_count": 2,
            "textrazor_sense_score": 0.91,
            "textrazor_spelling_suggestion_count": 1,
            "textrazor_relation_count": 2,
            "textrazor_property_count": 1,
            "textrazor_noun_phrase_count": 3,
            "textrazor_top_noun_phrase_texts": [],
            "textrazor_relation_predicate_labels": [],
            "textrazor_relation_param_labels": [],
            "textrazor_property_names": ["crawlability"],
            "textrazor_dependency_depth_mean": 0.5,
            "textrazor_dependency_relation_type_count": 2,
            "textrazor_part_of_speech_type_count": 2,
            "textrazor_entity_mention_count": 2,
            "textrazor_unique_entity_count": 2,
            "textrazor_unique_entity_density_per_1k_words": 1000.0,
            "textrazor_entity_mention_density_per_1k_words": 1000.0,
            "textrazor_entities_present": True,
            "textrazor_topics_present": True,
            "textrazor_categories_present": True,
            "textrazor_entailments_present": True,
            "textrazor_words_present": True,
            "textrazor_relations_present": True,
            "textrazor_properties_present": True,
            "textrazor_noun_phrases_present": True,
            "textrazor_dependency_trees_present": True,
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
    response["response"].pop("sentences")
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
            "textrazor_top_topic_label": None,
            "textrazor_top_topic_score": None,
            "textrazor_category_score": None,
            "textrazor_classifier_score": None,
            "textrazor_top_category_label": None,
            "textrazor_top_category_classifier_id": None,
            "textrazor_entailment_score": None,
            "textrazor_entailment_prior": None,
            "textrazor_entailment_context": None,
            "textrazor_word_count": None,
            "textrazor_sense_score": None,
            "textrazor_spelling_suggestion_count": None,
            "textrazor_relation_count": None,
            "textrazor_property_count": None,
            "textrazor_noun_phrase_count": None,
            "textrazor_top_noun_phrase_texts": None,
            "textrazor_relation_predicate_labels": None,
            "textrazor_relation_param_labels": None,
            "textrazor_property_names": None,
            "textrazor_dependency_depth_mean": None,
            "textrazor_dependency_relation_type_count": None,
            "textrazor_part_of_speech_type_count": None,
            "textrazor_entity_mention_count": 2,
            "textrazor_unique_entity_count": 2,
            "textrazor_unique_entity_density_per_1k_words": None,
            "textrazor_entity_mention_density_per_1k_words": None,
            "textrazor_entities_present": True,
            "textrazor_topics_present": False,
            "textrazor_categories_present": False,
            "textrazor_entailments_present": False,
            "textrazor_words_present": False,
            "textrazor_relations_present": False,
            "textrazor_properties_present": False,
            "textrazor_noun_phrases_present": False,
            "textrazor_dependency_trees_present": False,
            "textrazor_page_metrics_complete": False,
            "schema_version": "curated.v1",
        }
    ]


def test_entity_dedupe_key_prefers_english_id_then_entity_id_then_matched_text() -> None:
    from seo_rank.textrazor import entity_dedupe_key

    assert entity_dedupe_key({"entityEnglishId": "en-1", "entityId": "id-1", "matchedText": "a"}) == "en-1"
    assert entity_dedupe_key({"entityId": "id-1", "matchedText": "a"}) == "id-1"
    assert entity_dedupe_key({"matchedText": "a"}) == "a"


def test_count_entities_dedupes_and_nulls_when_section_absent() -> None:
    from seo_rank.textrazor import count_entities

    entities = [
        {"entityEnglishId": "same", "entityId": "a", "matchedText": "A"},
        {"entityEnglishId": "same", "entityId": "b", "matchedText": "B"},
        {"entityId": "c", "matchedText": "C"},
    ]
    assert count_entities(entities, section_present=True) == {
        "mention_count": 3,
        "unique_count": 2,
    }
    assert count_entities([], section_present=False) is None


def test_normalize_page_metrics_materializes_entity_counts_and_word_densities() -> None:
    from seo_rank.textrazor import normalize_page_metrics

    response = fixture_page_metrics_response(
        url="https://example.com/technical-seo/1",
        text="Technical SEO helps crawlers discover important pages.",
    )
    # Duplicate English ID should collapse unique count but keep mention count.
    response["response"]["entities"].append(
        {
            "entityEnglishId": "technical-seo",
            "entityId": "technical-seo-alias",
            "matchedText": "Technical SEO",
            "confidenceScore": 1.0,
            "relevanceScore": 0.5,
            "type": ["Topic"],
        }
    )
    response["response"]["entities"][0]["entityEnglishId"] = "technical-seo"

    metrics = normalize_page_metrics(response, url="https://example.com/technical-seo/1")

    assert metrics["textrazor_entity_mention_count"] == 3
    assert metrics["textrazor_unique_entity_count"] == 2  # technical-seo + crawler
    # word_count = 2 from fixture
    assert metrics["textrazor_unique_entity_density_per_1k_words"] == 1000.0
    assert metrics["textrazor_entity_mention_density_per_1k_words"] == 1500.0


def test_normalize_page_metrics_nulls_entity_density_when_entities_absent() -> None:
    from seo_rank.textrazor import normalize_page_metrics

    response = fixture_page_metrics_response(
        url="https://example.com/technical-seo/1",
        text="Technical SEO helps crawlers discover important pages.",
    )
    response["response"].pop("entities")

    metrics = normalize_page_metrics(response, url="https://example.com/technical-seo/1")

    assert metrics["textrazor_entity_mention_count"] is None
    assert metrics["textrazor_unique_entity_count"] is None
    assert metrics["textrazor_unique_entity_density_per_1k_words"] is None
    assert metrics["textrazor_entity_mention_density_per_1k_words"] is None


def test_normalize_page_metrics_nulls_word_density_when_word_count_non_positive() -> None:
    from seo_rank.textrazor import normalize_page_metrics

    response = fixture_page_metrics_response(
        url="https://example.com/technical-seo/1",
        text="Technical SEO helps crawlers discover important pages.",
    )
    response["response"]["sentences"] = []

    metrics = normalize_page_metrics(response, url="https://example.com/technical-seo/1")

    assert metrics["textrazor_entity_mention_count"] == 2
    assert metrics["textrazor_unique_entity_count"] == 2
    assert metrics["textrazor_word_count"] == 0
    assert metrics["textrazor_unique_entity_density_per_1k_words"] is None
    assert metrics["textrazor_entity_mention_density_per_1k_words"] is None


def test_normalize_page_metrics_uses_sentence_words_for_sense_and_spelling() -> None:
    from seo_rank.textrazor import normalize_page_metrics

    response = fixture_page_metrics_response(
        url="https://example.com/technical-seo/1",
        text="Technical SEO helps crawlers discover important pages.",
    )
    response["response"]["words"] = [{"isGrammar": True, "isSense": True, "isSpelling": True}]
    response["response"]["sentences"] = [
        {
            "words": [
                {"token": "Technical", "senses": [{"score": 0.31}]},
                {
                    "token": "SEO",
                    "senses": [{"score": 0.91}, {"score": 0.73}],
                    "spellingSuggestions": ["sea", "see"],
                },
            ]
        },
        {
            "words": [
                {"token": "helps", "spellingSuggestions": []},
            ]
        },
    ]

    metrics = normalize_page_metrics(response, url="https://example.com/technical-seo/1")

    assert metrics["textrazor_word_count"] == 3
    assert metrics["textrazor_sense_score"] == 0.91
    assert metrics["textrazor_spelling_suggestion_count"] == 1
    assert metrics["textrazor_words_present"] is True


def test_normalize_page_metrics_materializes_dependency_tree_complexity() -> None:
    response = fixture_page_metrics_response(
        url="https://example.com/technical-seo/1",
        text="Technical SEO helps crawlers discover important pages.",
    )
    response["response"]["sentences"] = [
        {
            "words": [
                {
                    "position": 0,
                    "parentPosition": -1,
                    "relationToParent": "ROOT",
                    "partOfSpeech": "NOUN",
                },
                {
                    "position": 1,
                    "parentPosition": 0,
                    "relationToParent": "nsubj",
                    "partOfSpeech": "NOUN",
                },
                {
                    "position": 2,
                    "parentPosition": 1,
                    "relationToParent": "amod",
                    "partOfSpeech": "ADJ",
                },
            ]
        }
    ]

    metrics = normalize_page_metrics(response, url="https://example.com/technical-seo/1")

    assert metrics["textrazor_dependency_trees_present"] is True
    assert metrics["textrazor_dependency_depth_mean"] == 1.0
    assert metrics["textrazor_dependency_relation_type_count"] == 3
    assert metrics["textrazor_part_of_speech_type_count"] == 2


def test_normalize_page_metrics_skips_invalid_dependency_links() -> None:
    response = fixture_page_metrics_response(
        url="https://example.com/technical-seo/1",
        text="Technical SEO helps crawlers discover important pages.",
    )
    response["response"]["sentences"] = [
        {
            "words": [
                {
                    "position": 0,
                    "parentPosition": -1,
                    "relationToParent": "ROOT",
                    "partOfSpeech": "NOUN",
                },
                {
                    "position": 1,
                    "parentPosition": 0,
                    "relationToParent": "nsubj",
                    "partOfSpeech": "VERB",
                },
                {
                    "position": 2,
                    "parentPosition": 99,
                    "relationToParent": "orphan",
                    "partOfSpeech": "ADJ",
                },
                {
                    "position": 3,
                    "parentPosition": 4,
                    "relationToParent": "cycle",
                    "partOfSpeech": "ADV",
                },
                {
                    "position": 4,
                    "parentPosition": 3,
                    "relationToParent": "cycle",
                    "partOfSpeech": "ADV",
                },
            ]
        }
    ]

    metrics = normalize_page_metrics(response, url="https://example.com/technical-seo/1")

    assert metrics["textrazor_dependency_depth_mean"] == 0.5
    assert metrics["textrazor_dependency_relation_type_count"] == 2
    assert metrics["textrazor_part_of_speech_type_count"] == 2


def test_normalize_page_metrics_nulls_dependency_metrics_when_annotations_absent() -> None:
    response = fixture_page_metrics_response(
        url="https://example.com/technical-seo/1",
        text="Technical SEO helps crawlers discover important pages.",
    )
    for word in response["response"]["sentences"][0]["words"]:
        word.pop("position")
        word.pop("parentPosition")
        word.pop("relationToParent")
        word.pop("partOfSpeech")

    metrics = normalize_page_metrics(response, url="https://example.com/technical-seo/1")

    assert metrics["textrazor_dependency_trees_present"] is False
    assert metrics["textrazor_dependency_depth_mean"] is None
    assert metrics["textrazor_dependency_relation_type_count"] is None
    assert metrics["textrazor_part_of_speech_type_count"] is None
