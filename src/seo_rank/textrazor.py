"""Offline TextRazor fixture boundaries."""
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
import logging
import urllib.parse
import urllib.request
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from seo_rank.domain_blocklist import DomainBlocklist

logger = logging.getLogger(__name__)

TEXTRAZOR_RESPONSE_SECTIONS = (
    "entities",
    "topics",
    "categories",
    "entailments",
    "words",
    "relations",
    "properties",
    "nounPhrases",
)

TEXTRAZOR_BASE_URL = "https://api.textrazor.com"
TEXTRAZOR_PAGE_METRIC_EXTRACTORS = (
    "entities",
    "topics",
    "words",
    "phrases",
    "dependency-trees",
    "relations",
    "entailments",
    "senses",
    "spelling",
)

TEXTRAZOR_PAGE_METRIC_CLASSIFIERS = (
    "textrazor_mediatopics_2023Q1",
    "textrazor_iab_content_taxonomy_3.0",
)
STRUCTURED_TEXT_LIMIT = 3


@dataclass(frozen=True)
class TextRazorEndpoint:
    extractor: str
    raw_response_endpoint: str
    request_path: str


TEXTRAZOR_ENDPOINTS = {
    "entities": TextRazorEndpoint(
        extractor="entities",
        raw_response_endpoint="entities",
        request_path="/",
    ),
    "page_metrics": TextRazorEndpoint(
        extractor=",".join(TEXTRAZOR_PAGE_METRIC_EXTRACTORS),
        raw_response_endpoint="entities",
        request_path="/",
    ),
}


@dataclass(frozen=True)
class TextRazorRequest:
    method: str
    path: str
    headers: dict[str, str]
    body: dict[str, str]


@dataclass(frozen=True)
class TextRazorCredentials:
    api_key: str


class TextRazorCredentialError(ValueError):
    """Raised when required TextRazor credentials are missing."""


class TextRazorClientError(RuntimeError):
    """Raised when a TextRazor HTTP request fails."""


def build_entity_request(page_text: Mapping[str, str]) -> TextRazorRequest:
    """Build a TextRazor entity extraction request from parsed page text."""

    endpoint = TEXTRAZOR_ENDPOINTS["page_metrics"]
    return TextRazorRequest(
        method="POST",
        path=endpoint.request_path,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        body={
            "extractors": endpoint.extractor,
            "classifiers": ",".join(TEXTRAZOR_PAGE_METRIC_CLASSIFIERS),
            "text": str(page_text["text"]),
        },
    )


def pages_missing_textrazor(
    pages: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    """Return first-seen, non-blank pages that should be sent to TextRazor."""

    deduped: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()
    for page in pages:
        if not isinstance(page, Mapping):
            continue
        target_keyword = page.get("target_keyword")
        url = page.get("url")
        text = page.get("text")
        if not isinstance(target_keyword, str) or not target_keyword.strip():
            continue
        if not isinstance(url, str) or not url.strip():
            continue
        if not isinstance(text, str) or not text.strip():
            continue
        identity = (target_keyword.casefold().strip(), url.strip())
        if identity in seen:
            continue
        seen.add(identity)
        deduped.append(dict(page))
    return deduped


def fetch_textrazor_entities_for_pages(
    pages: Sequence[Mapping[str, object]],
    *,
    credentials: TextRazorCredentials,
    transport=None,
    timeout: float = 30.0,
    blocklist: DomainBlocklist | None = None,
) -> list[dict[str, object]]:
    """Fetch TextRazor entity responses for unique parsed page records."""

    page_batch = pages_missing_textrazor(pages)
    if blocklist is not None:
        page_batch = blocklist.filter_results(page_batch)
    if page_batch:
        logger.info("textrazor batch start pages=%d", len(page_batch))

    responses: list[dict[str, object]] = []
    for page_text in page_batch:
        url = str(page_text["url"])
        text = str(page_text["text"])
        logger.info(
            "textrazor request url=%s text_chars=%d extractors=%s",
            url,
            len(text),
            TEXTRAZOR_ENDPOINTS["page_metrics"].extractor,
        )
        response = execute_textrazor_request(
            build_entity_request(page_text),
            credentials=credentials,
            transport=transport,
            timeout=timeout,
        )
        summary = summarize_textrazor_response(response)
        _log_textrazor_response(url=url, summary=summary)
        responses.append(
            response
            | {
                "url": url,
                "source_text": text,
            }
        )
    if page_batch:
        logger.info("textrazor batch done responses=%d", len(responses))
    return responses


def validate_textrazor_credentials(
    env: Mapping[str, str],
    *,
    required: str = "TEXTRAZOR_API_KEY",
) -> TextRazorCredentials:
    """Validate TextRazor credentials without exposing values in errors."""

    if not env.get(required, "").strip():
        raise TextRazorCredentialError(f"Missing TextRazor credential: {required}")
    return TextRazorCredentials(api_key=env[required].strip())


def execute_textrazor_request(
    request: TextRazorRequest,
    *,
    credentials: TextRazorCredentials,
    transport=None,
    timeout: float = 30.0,
) -> dict[str, object]:
    """Execute a TextRazor request and parse the JSON response."""

    if transport is None:
        transport = urllib_form_transport
    body = urllib.parse.urlencode(request.body).encode("utf-8")
    response = transport(
        method=request.method,
        url=f"{TEXTRAZOR_BASE_URL}{request.path}",
        headers={
            **request.headers,
            "X-TextRazor-Key": credentials.api_key,
        },
        body=body,
        timeout=timeout,
    )
    if not isinstance(response, dict):
        raise TextRazorClientError("TextRazor response was not a JSON object")
    error = response.get("error")
    if isinstance(error, Mapping):
        logger.warning(
            "textrazor api error code=%s message=%s",
            error.get("code"),
            error.get("message"),
        )
    elif error is not None:
        logger.warning("textrazor api error payload=%r", error)
    return response


def urllib_form_transport(
    *,
    method: str,
    url: str,
    headers: dict[str, str],
    body: bytes,
    timeout: float,
) -> object:
    http_request = urllib.request.Request(
        url,
        data=body,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(http_request, timeout=timeout) as response:
            payload = response.read()
    except OSError as error:
        raise TextRazorClientError(f"TextRazor request failed: {error}") from error
    return json.loads(payload.decode("utf-8"))


def fixture_entity_response(url: str, text: str) -> dict[str, object]:
    """Return a deterministic TextRazor-shaped entity extraction fixture."""

    return {
        "provider": "textrazor",
        "url": url,
        "response": {
            "language": "eng",
            "entities": [
                {
                    "entityId": "technical-seo",
                    "matchedText": "Technical SEO",
                    "confidenceScore": 7.5,
                    "relevanceScore": 0.92,
                    "type": ["Topic", "SEO"],
                },
                {
                    "entityId": "crawler",
                    "matchedText": "crawlers",
                    "confidenceScore": 5.5,
                    "relevanceScore": 0.71,
                    "type": ["SoftwareAgent"],
                },
            ],
        },
        "source_text": text,
    }


def fixture_page_metrics_response(url: str, text: str) -> dict[str, object]:
    """Return a deterministic TextRazor-shaped page metrics fixture."""

    return {
        "provider": "textrazor",
        "url": url,
        "response": {
            "language": "eng",
            "entities": [
                {
                    "entityId": "technical-seo",
                    "matchedText": "Technical SEO",
                    "confidenceScore": 7.5,
                    "relevanceScore": 0.92,
                    "type": ["Topic", "SEO"],
                },
                {
                    "entityId": "crawler",
                    "matchedText": "crawlers",
                    "confidenceScore": 5.5,
                    "relevanceScore": 0.71,
                    "type": ["SoftwareAgent"],
                },
            ],
            "topics": [
                {"label": "Technical SEO", "score": 0.66},
                {"label": "Search crawling", "score": 0.41},
            ],
            "categories": [
                {
                    "label": "Search engine optimization",
                    "score": 0.83,
                    "classifierScore": 0.74,
                    "classifierId": "textrazor_mediatopics_2023Q1",
                },
            ],
            "entailments": [
                {"term": "crawlers", "score": 0.61, "priorScore": 0.34, "contextScore": 0.27},
            ],
            "sentences": [
                {
                    "words": [
                        {
                            "token": "Technical",
                            "position": 0,
                            "parentPosition": -1,
                            "relationToParent": "ROOT",
                            "partOfSpeech": "NOUN",
                            "senses": [{"score": 0.42}],
                        },
                        {
                            "token": "SEO",
                            "position": 1,
                            "parentPosition": 0,
                            "relationToParent": "compound",
                            "partOfSpeech": "PROPN",
                            "senses": [{"score": 0.91}, {"score": 0.73}],
                            "spellingSuggestions": ["sea"],
                        },
                    ]
                }
            ],
            "relations": [
                {"subject": "Technical SEO", "object": "crawlers"},
                {"subject": "crawlers", "object": "pages"},
            ],
            "properties": [
                {"name": "crawlability"},
            ],
            "nounPhrases": [
                {"text": "Technical SEO"},
                {"text": "important pages"},
                {"text": "search crawlers"},
            ],
        },
        "source_text": text,
    }


def normalize_entities(
    response: Mapping[str, Any],
    *,
    url: str,
) -> list[dict[str, object]]:
    """Normalize TextRazor entities into stable rows for run artifacts."""

    normalized: list[dict[str, object]] = []
    payload = response.get("response", {})
    if not isinstance(payload, Mapping):
        logger.info("textrazor normalize entities url=%s entities=0 (missing response payload)", url)
        return normalized

    entities = payload.get("entities", [])
    if not isinstance(entities, list):
        logger.info("textrazor normalize entities url=%s entities=0 (invalid entities list)", url)
        return normalized

    for entity in entities:
        if not isinstance(entity, Mapping):
            continue
        entity_id = entity.get("entityId")
        matched_text = entity.get("matchedText")
        confidence = entity.get("confidenceScore")
        relevance = entity.get("relevanceScore")
        types = entity.get("type", [])
        if not isinstance(entity_id, str) or not isinstance(matched_text, str):
            continue
        if not isinstance(confidence, int | float):
            confidence = 0.0
        if not isinstance(relevance, int | float):
            relevance = 0.0
        if not isinstance(types, list):
            types = []
        normalized.append(
            {
                "url": url,
                "entity_id": entity_id,
                "entity_english_id": _optional_string(entity.get("entityEnglishId")),
                "matched_text": matched_text,
                "confidence": float(confidence),
                "relevance": float(relevance),
                "types": [value for value in types if isinstance(value, str)],
                "wikidata_id": _optional_string(entity.get("wikidataId")),
                "wiki_link": _optional_string(entity.get("wikiLink")),
                "freebase_types": _string_values(entity.get("freebaseTypes")),
                "enriched_data_keys": _enriched_data_keys(entity.get("data")),
            }
        )
    logger.info(
        "textrazor normalize entities url=%s entities=%d top=%s",
        url,
        len(normalized),
        [entity["entity_id"] for entity in normalized[:3]],
    )
    return normalized


def _optional_string(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    return value.strip() or None


def _string_values(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _enriched_data_keys(value: object) -> list[str]:
    if not isinstance(value, Mapping):
        return []
    return sorted(
        key.strip() for key in value if isinstance(key, str) and key.strip()
    )[:STRUCTURED_TEXT_LIMIT]


def normalize_page_metrics(
    response: Mapping[str, Any],
    *,
    url: str,
) -> dict[str, object]:
    """Normalize page-level TextRazor metrics into stable scalar signals."""

    payload = response.get("response", {})
    if not isinstance(payload, Mapping):
        payload = {}

    entities, entities_present = _section_rows(payload, "entities")
    topics, topics_present = _section_rows(payload, "topics")
    categories, categories_present = _section_rows(payload, "categories")
    entailments, entailments_present = _section_rows(payload, "entailments")
    words, words_present = _sentence_words(payload)
    relations, relations_present = _section_rows(payload, "relations")
    properties, properties_present = _section_rows(payload, "properties")
    noun_phrases, noun_phrases_present = _section_rows(payload, "nounPhrases")
    dependency_metrics = _dependency_tree_metrics(payload)
    top_topic = _top_labeled_score_row(topics, section_present=topics_present)
    top_category = _top_labeled_score_row(categories, section_present=categories_present)
    section_presence = (
        entities_present,
        topics_present,
        categories_present,
        entailments_present,
        words_present,
        relations_present,
        properties_present,
        noun_phrases_present,
        dependency_metrics["textrazor_dependency_trees_present"],
    )
    metrics = {
        "url": url,
        "textrazor_entity_confidence_score": _max_numeric(
            entities,
            ("confidenceScore",),
            section_present=entities_present,
        ),
        "textrazor_entity_relevance_score": _max_numeric(
            entities,
            ("relevanceScore",),
            section_present=entities_present,
        ),
        "textrazor_topic_score": _max_numeric(
            topics,
            ("score",),
            section_present=topics_present,
        ),
        "textrazor_top_topic_label": top_topic["label"] if top_topic else None,
        "textrazor_top_topic_score": top_topic["score"] if top_topic else None,
        "textrazor_category_score": _max_numeric(
            categories,
            ("score",),
            section_present=categories_present,
        ),
        "textrazor_classifier_score": _max_numeric(
            categories,
            ("classifierScore", "score"),
            section_present=categories_present,
        ),
        "textrazor_top_category_label": top_category["label"] if top_category else None,
        "textrazor_top_category_classifier_id": (
            top_category["classifier_id"] if top_category else None
        ),
        "textrazor_entailment_score": _max_numeric(
            entailments,
            ("score",),
            section_present=entailments_present,
        ),
        "textrazor_entailment_prior": _max_numeric(
            entailments,
            ("priorScore",),
            section_present=entailments_present,
        ),
        "textrazor_entailment_context": _max_numeric(
            entailments,
            ("contextScore",),
            section_present=entailments_present,
        ),
        "textrazor_word_count": _count_rows(words, section_present=words_present),
        "textrazor_sense_score": _max_nested_numeric(
            words,
            collection_key="senses",
            value_key="score",
            section_present=words_present,
        ),
        "textrazor_spelling_suggestion_count": _count_nonempty_collections(
            words,
            "spellingSuggestions",
            section_present=words_present,
        ),
        "textrazor_relation_count": _count_rows(relations, section_present=relations_present),
        "textrazor_property_count": _count_rows(properties, section_present=properties_present),
        "textrazor_noun_phrase_count": _count_rows(
            noun_phrases,
            section_present=noun_phrases_present,
        ),
        "textrazor_top_noun_phrase_texts": _noun_phrase_texts(
            noun_phrases,
            words,
            section_present=noun_phrases_present,
        ),
        "textrazor_relation_predicate_labels": _relation_predicate_labels(
            relations,
            section_present=relations_present,
        ),
        "textrazor_relation_param_labels": _relation_param_labels(
            relations,
            words,
            section_present=relations_present,
        ),
        "textrazor_property_names": _property_names(
            properties,
            section_present=properties_present,
        ),
        **dependency_metrics,
        **_entity_count_metrics(entities, entities_present=entities_present, word_count=_count_rows(words, section_present=words_present)),
        "textrazor_entities_present": entities_present,
        "textrazor_topics_present": topics_present,
        "textrazor_categories_present": categories_present,
        "textrazor_entailments_present": entailments_present,
        "textrazor_words_present": words_present,
        "textrazor_relations_present": relations_present,
        "textrazor_properties_present": properties_present,
        "textrazor_noun_phrases_present": noun_phrases_present,
        "textrazor_page_metrics_complete": all(section_presence),
    }
    logger.info(
        "textrazor normalize metrics url=%s complete=%s "
        "entity_confidence=%s entity_relevance=%s topic_score=%s category_score=%s "
        "word_count=%s relation_count=%s noun_phrase_count=%s",
        url,
        metrics["textrazor_page_metrics_complete"],
        metrics["textrazor_entity_confidence_score"],
        metrics["textrazor_entity_relevance_score"],
        metrics["textrazor_topic_score"],
        metrics["textrazor_category_score"],
        metrics["textrazor_word_count"],
        metrics["textrazor_relation_count"],
        metrics["textrazor_noun_phrase_count"],
    )
    return metrics


def summarize_textrazor_response(response: Mapping[str, Any]) -> dict[str, object]:
    """Summarize a TextRazor API response for logging."""

    payload = response.get("response", {})
    if not isinstance(payload, Mapping):
        payload = {}

    section_counts = {
        section: _section_row_count(payload, section)
        for section in TEXTRAZOR_RESPONSE_SECTIONS
    }
    entities = payload.get("entities", [])
    top_entities: list[str] = []
    if isinstance(entities, list):
        for entity in entities[:3]:
            if isinstance(entity, Mapping) and isinstance(entity.get("entityId"), str):
                top_entities.append(entity["entityId"])

    language = payload.get("language")
    error = response.get("error")
    if isinstance(error, Mapping):
        error_value: object = {
            "code": error.get("code"),
            "message": error.get("message"),
        }
    else:
        error_value = error

    return {
        "language": language if isinstance(language, str) else None,
        "section_counts": section_counts,
        "top_entities": top_entities,
        "error": error_value,
    }


def _log_textrazor_response(*, url: str, summary: Mapping[str, object]) -> None:
    section_counts = summary.get("section_counts", {})
    if not isinstance(section_counts, Mapping):
        section_counts = {}
    section_parts = [
        f"{section}={section_counts.get(section, 0)}"
        for section in TEXTRAZOR_RESPONSE_SECTIONS
    ]
    top_entities = summary.get("top_entities", [])
    if not isinstance(top_entities, list):
        top_entities = []
    top_entity_text = ",".join(str(entity) for entity in top_entities) or "-"
    logger.info(
        "textrazor response url=%s language=%s %s top_entities=%s error=%s",
        url,
        summary.get("language") or "-",
        " ".join(section_parts),
        top_entity_text,
        summary.get("error"),
    )


def _section_row_count(payload: Mapping[str, Any], key: str) -> int:
    if key == "words":
        words, words_present = _sentence_words(payload)
        return len(words) if words_present else 0
    value = payload.get(key)
    if not isinstance(value, list):
        return 0
    return sum(1 for item in value if isinstance(item, Mapping))




def _entity_count_metrics(
    entities: list[Mapping[str, Any]],
    *,
    entities_present: bool,
    word_count: int | None,
) -> dict[str, object]:
    counts = count_entities(entities, section_present=entities_present)
    if counts is None:
        return {
            "textrazor_entity_mention_count": None,
            "textrazor_unique_entity_count": None,
            "textrazor_unique_entity_density_per_1k_words": None,
            "textrazor_entity_mention_density_per_1k_words": None,
        }
    mention = counts["mention_count"]
    unique = counts["unique_count"]
    return {
        "textrazor_entity_mention_count": mention,
        "textrazor_unique_entity_count": unique,
        "textrazor_unique_entity_density_per_1k_words": _entity_density_per_1k(
            unique, word_count
        ),
        "textrazor_entity_mention_density_per_1k_words": _entity_density_per_1k(
            mention, word_count
        ),
    }


def entity_dedupe_key(entity: Mapping[str, Any]) -> str:
    """Canonical unique-entity key: EnglishId → entityId → matchedText."""

    for key in ("entityEnglishId", "entityId", "matchedText"):
        value = entity.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def count_entities(
    entities: Sequence[Mapping[str, Any]],
    *,
    section_present: bool,
) -> dict[str, int] | None:
    """Return mention/unique entity counts, or None when the section is absent."""

    if not section_present:
        return None
    unique_keys = {entity_dedupe_key(entity) for entity in entities}
    return {
        "mention_count": len(entities),
        "unique_count": len(unique_keys),
    }


def _entity_density_per_1k(count: int | None, denominator: int | None) -> float | None:
    if count is None or denominator is None or denominator <= 0:
        return None
    return float(count) * 1000.0 / float(denominator)


def _section_rows(
    payload: Mapping[str, Any],
    key: str,
) -> tuple[list[Mapping[str, Any]], bool]:
    value = payload.get(key)
    if not isinstance(value, list):
        return [], False
    return [item for item in value if isinstance(item, Mapping)], True


def _sentence_words(payload: Mapping[str, Any]) -> tuple[list[Mapping[str, Any]], bool]:
    sentences = payload.get("sentences")
    if not isinstance(sentences, list):
        return [], False
    words: list[Mapping[str, Any]] = []
    for sentence in sentences:
        if not isinstance(sentence, Mapping):
            continue
        sentence_words = sentence.get("words")
        if not isinstance(sentence_words, list):
            continue
        words.extend(word for word in sentence_words if isinstance(word, Mapping))
    return words, True


def _dependency_tree_metrics(payload: Mapping[str, Any]) -> dict[str, object]:
    """Summarize valid per-word dependency annotations into page scalars."""

    sentences = payload.get("sentences")
    if not isinstance(sentences, list):
        return _empty_dependency_tree_metrics(present=False)
    words, _ = _sentence_words(payload)
    if not words:
        return _empty_dependency_tree_metrics(present=True)

    nodes: dict[int, tuple[int, str, str]] = {}
    duplicate_positions: set[int] = set()
    for word in words:
        position = word.get("position")
        parent_position = word.get("parentPosition")
        relation = word.get("relationToParent")
        part_of_speech = word.get("partOfSpeech")
        if (
            not isinstance(position, int)
            or isinstance(position, bool)
            or not isinstance(parent_position, int)
            or isinstance(parent_position, bool)
            or not isinstance(relation, str)
            or not relation.strip()
            or not isinstance(part_of_speech, str)
            or not part_of_speech.strip()
        ):
            continue
        if position in nodes:
            duplicate_positions.add(position)
            continue
        nodes[position] = (parent_position, relation, part_of_speech)
    for position in duplicate_positions:
        nodes.pop(position, None)
    if not nodes:
        return _empty_dependency_tree_metrics(present=False)

    valid_nodes: list[tuple[int, str, str]] = []
    for position, node in nodes.items():
        depth = _dependency_depth(position, nodes)
        if depth is not None:
            valid_nodes.append((depth, node[1], node[2]))
    if not valid_nodes:
        return _empty_dependency_tree_metrics(present=True)
    depths, relations, parts_of_speech = zip(*valid_nodes, strict=True)
    return {
        "textrazor_dependency_depth_mean": sum(depths) / len(depths),
        "textrazor_dependency_relation_type_count": len(set(relations)),
        "textrazor_part_of_speech_type_count": len(set(parts_of_speech)),
        "textrazor_dependency_trees_present": True,
    }


def _empty_dependency_tree_metrics(*, present: bool) -> dict[str, object]:
    return {
        "textrazor_dependency_depth_mean": None,
        "textrazor_dependency_relation_type_count": None,
        "textrazor_part_of_speech_type_count": None,
        "textrazor_dependency_trees_present": present,
    }


def _dependency_depth(
    position: int,
    nodes: Mapping[int, tuple[int, str, str]],
) -> int | None:
    """Return a token's root-relative depth, or None for malformed chains."""

    depth = 0
    current = position
    visited: set[int] = set()
    while True:
        if current in visited:
            return None
        visited.add(current)
        parent_position = nodes[current][0]
        if parent_position < 0 or parent_position == current:
            return depth
        if parent_position not in nodes:
            return None
        depth += 1
        current = parent_position


def _max_numeric(
    rows: list[Mapping[str, Any]],
    candidate_keys: tuple[str, ...],
    *,
    section_present: bool,
) -> float | None:
    if not section_present:
        return None
    values: list[float] = []
    for row in rows:
        for key in candidate_keys:
            value = row.get(key)
            if isinstance(value, int | float):
                values.append(float(value))
                break
    return max(values) if values else 0.0


def _top_labeled_score_row(
    rows: list[Mapping[str, Any]],
    *,
    section_present: bool,
) -> dict[str, str | float] | None:
    """Return the first highest-scoring labeled TextRazor row."""

    if not section_present:
        return None
    top: dict[str, str | float] | None = None
    for row in rows:
        label = row.get("label")
        score = row.get("score")
        if not isinstance(label, str) or not label.strip():
            continue
        if not isinstance(score, int | float):
            continue
        candidate = {
            "label": label,
            "score": float(score),
            "classifier_id": row.get("classifierId")
            if isinstance(row.get("classifierId"), str)
            else None,
        }
        if top is None or candidate["score"] > top["score"]:
            top = candidate
    return top


def _noun_phrase_texts(
    noun_phrases: list[Mapping[str, Any]],
    words: list[Mapping[str, Any]],
    *,
    section_present: bool,
) -> list[str] | None:
    if not section_present:
        return None
    return _bounded_distinct_texts(
        _text_from_word_positions(noun_phrase, words) for noun_phrase in noun_phrases
    )


def _relation_predicate_labels(
    relations: list[Mapping[str, Any]],
    *,
    section_present: bool,
) -> list[str] | None:
    if not section_present:
        return None
    return _bounded_distinct_texts(relation.get("relation") for relation in relations)


def _relation_param_labels(
    relations: list[Mapping[str, Any]],
    words: list[Mapping[str, Any]],
    *,
    section_present: bool,
) -> list[str] | None:
    if not section_present:
        return None
    labels: list[str | None] = []
    for relation in relations:
        params = relation.get("params")
        if not isinstance(params, list):
            continue
        for param in params:
            if not isinstance(param, Mapping):
                continue
            name = param.get("name")
            text = _text_from_word_positions(param, words)
            if isinstance(name, str) and name.strip() and text is not None:
                labels.append(f"{name}: {text}")
    return _bounded_distinct_texts(labels)


def _property_names(
    properties: list[Mapping[str, Any]],
    *,
    section_present: bool,
) -> list[str] | None:
    if not section_present:
        return None
    return _bounded_distinct_texts(property_.get("name") for property_ in properties)


def _text_from_word_positions(
    row: Mapping[str, Any],
    words: list[Mapping[str, Any]],
) -> str | None:
    positions = row.get("wordPositions")
    if not isinstance(positions, list) or not positions:
        return None
    tokens: list[str] = []
    for position in positions:
        if not isinstance(position, int) or isinstance(position, bool):
            return None
        if position < 0 or position >= len(words):
            return None
        token = words[position].get("token")
        if not isinstance(token, str) or not token.strip():
            return None
        tokens.append(token)
    return " ".join(tokens)


def _bounded_distinct_texts(values: Sequence[object]) -> list[str]:
    values_out: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, str):
            continue
        text = value.strip()
        if not text or text in seen:
            continue
        seen.add(text)
        values_out.append(text)
        if len(values_out) == STRUCTURED_TEXT_LIMIT:
            break
    return values_out


def _count_rows(rows: list[Mapping[str, Any]], *, section_present: bool) -> int | None:
    if not section_present:
        return None
    return len(rows)


def _max_nested_numeric(
    rows: list[Mapping[str, Any]],
    *,
    collection_key: str,
    value_key: str,
    section_present: bool,
) -> float | None:
    if not section_present:
        return None
    values: list[float] = []
    for row in rows:
        nested = row.get(collection_key)
        if not isinstance(nested, list):
            continue
        for item in nested:
            if isinstance(item, Mapping) and isinstance(item.get(value_key), int | float):
                values.append(float(item[value_key]))
    return max(values) if values else 0.0


def _count_nonempty_collections(
    rows: list[Mapping[str, Any]],
    key: str,
    *,
    section_present: bool,
) -> int | None:
    if not section_present:
        return None
    return sum(
        1
        for row in rows
        if isinstance(row.get(key), list) and bool(row[key])
    )
