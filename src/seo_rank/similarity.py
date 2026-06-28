"""Deterministic fixture embedding similarity features."""

import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Any

Vector = tuple[float, ...]


def compute_page_similarity_features(
    keyword: str,
    passages: Sequence[Mapping[str, Any]],
) -> list[dict[str, object]]:
    keyword_vector = fixture_embedding(keyword)
    by_url: dict[str, list[dict[str, object]]] = defaultdict(list)

    for passage in passages:
        url = passage.get("url")
        passage_id = passage.get("passage_id")
        text = passage.get("text", "")
        if not isinstance(url, str) or not isinstance(passage_id, str):
            continue
        if not isinstance(text, str):
            text = ""
        passage_vector = fixture_embedding(text)
        by_url[url].append(
            {
                "passage_id": passage_id,
                "similarity": cosine_similarity(keyword_vector, passage_vector),
            }
        )

    features: list[dict[str, object]] = []
    for url, scored_passages in by_url.items():
        best = max(scored_passages, key=lambda item: item["similarity"])
        similarities = [float(item["similarity"]) for item in scored_passages]
        features.append(
            {
                "url": url,
                "passage_count": len(scored_passages),
                "max_similarity": round(float(best["similarity"]), 6),
                "mean_similarity": round(sum(similarities) / len(similarities), 6),
                "best_passage_id": best["passage_id"],
            }
        )
    return features


def fixture_embedding(text: str) -> Vector:
    normalized = text.casefold()
    if "technical seo" in normalized or "crawling" in normalized:
        return (1.0, 0.0)
    if "index" in normalized or "canonical" in normalized:
        return (1.0, 1.0)
    return (0.0, 1.0)


def cosine_similarity(left: Vector, right: Vector) -> float:
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    dot = sum(left_value * right_value for left_value, right_value in zip(left, right))
    return dot / (left_norm * right_norm)
