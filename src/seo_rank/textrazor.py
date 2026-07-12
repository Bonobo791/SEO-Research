"""Offline TextRazor fixture boundaries."""

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
    "relations",
    "entailments",
    "senses",
    "spelling",
)

TEXTRAZOR_PAGE_METRIC_CLASSIFIERS = ("textrazor_mediatopics_2023Q1",)


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
                {"label": "Search engine optimization", "score": 0.83, "classifierScore": 0.74},
            ],
            "entailments": [
                {"term": "crawlers", "score": 0.61, "priorScore": 0.34, "contextScore": 0.27},
            ],
            "words": [
                {"text": "Technical", "isGrammar": True, "isSense": False, "isSpelling": False},
                {"text": "SEO", "isGrammar": False, "isSense": True, "isSpelling": True},
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
                "matched_text": matched_text,
                "confidence": float(confidence),
                "relevance": float(relevance),
                "types": [value for value in types if isinstance(value, str)],
            }
        )
    logger.info(
        "textrazor normalize entities url=%s entities=%d top=%s",
        url,
        len(normalized),
        [entity["entity_id"] for entity in normalized[:3]],
    )
    return normalized


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
    words, words_present = _section_rows(payload, "words")
    relations, relations_present = _section_rows(payload, "relations")
    properties, properties_present = _section_rows(payload, "properties")
    noun_phrases, noun_phrases_present = _section_rows(payload, "nounPhrases")
    section_presence = (
        entities_present,
        topics_present,
        categories_present,
        entailments_present,
        words_present,
        relations_present,
        properties_present,
        noun_phrases_present,
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
        "textrazor_grammar_count": _count_truthy(
            words,
            ("isGrammar",),
            section_present=words_present,
        ),
        "textrazor_sense_count": _count_truthy(
            words,
            ("isSense",),
            section_present=words_present,
        ),
        "textrazor_spelling_count": _count_truthy(
            words,
            ("isSpelling",),
            section_present=words_present,
        ),
        "textrazor_relation_count": _count_rows(relations, section_present=relations_present),
        "textrazor_property_count": _count_rows(properties, section_present=properties_present),
        "textrazor_noun_phrase_count": _count_rows(
            noun_phrases,
            section_present=noun_phrases_present,
        ),
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
    value = payload.get(key)
    if not isinstance(value, list):
        return 0
    return sum(1 for item in value if isinstance(item, Mapping))


def _section_rows(
    payload: Mapping[str, Any],
    key: str,
) -> tuple[list[Mapping[str, Any]], bool]:
    value = payload.get(key)
    if not isinstance(value, list):
        return [], False
    return [item for item in value if isinstance(item, Mapping)], True


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


def _count_rows(rows: list[Mapping[str, Any]], *, section_present: bool) -> int | None:
    if not section_present:
        return None
    return len(rows)


def _count_truthy(
    rows: list[Mapping[str, Any]],
    candidate_keys: tuple[str, ...],
    *,
    section_present: bool,
) -> int | None:
    if not section_present:
        return None
    count = 0
    for row in rows:
        for key in candidate_keys:
            if bool(row.get(key)):
                count += 1
                break
    return count
