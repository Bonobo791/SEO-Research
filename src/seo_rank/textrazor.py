"""Offline TextRazor fixture boundaries."""

from collections.abc import Mapping
from typing import Any


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


def normalize_entities(
    response: Mapping[str, Any],
    *,
    url: str,
) -> list[dict[str, object]]:
    """Normalize TextRazor entities into stable rows for run artifacts."""

    normalized: list[dict[str, object]] = []
    payload = response.get("response", {})
    if not isinstance(payload, Mapping):
        return normalized

    entities = payload.get("entities", [])
    if not isinstance(entities, list):
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
    return normalized
