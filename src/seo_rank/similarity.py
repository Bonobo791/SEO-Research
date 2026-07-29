"""Deterministic fixture embedding similarity features."""
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


import math
import re
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


def compute_page_similarity_scores(
    keyword: str,
    pages: Sequence[Mapping[str, Any]],
) -> list[dict[str, object]]:
    keyword_vector = fixture_embedding(keyword)
    scores: list[dict[str, object]] = []

    for page in pages:
        url = page.get("url")
        text = page.get("text", "")
        if not isinstance(url, str):
            continue
        if not isinstance(text, str):
            text = ""

        gemini_score = round(
            cosine_similarity(keyword_vector, fixture_embedding(text)),
            6,
        )
        semantic_score = round(
            cosine_similarity(
                fixture_semantic_embedding(keyword),
                fixture_semantic_embedding(text),
            ),
            6,
        )
        bge_score = round(fixture_bge_reranker_score(keyword, text), 6)
        scores.append(
            {
                "url": url,
                "page_similarity": {
                    "bge": {
                        "raw_score": bge_score,
                        "normalized_score": bge_score,
                    },
                    "gemini_doc_retrieval": {
                        "raw_score": gemini_score,
                        "normalized_score": gemini_score,
                    },
                    "gemini_semantic_similarity": {
                        "raw_score": semantic_score,
                        "normalized_score": semantic_score,
                    },
                },
            }
        )

    return scores


def fixture_embedding(text: str) -> Vector:
    normalized = text.casefold()
    if "technical seo" in normalized or "crawling" in normalized:
        return (1.0, 0.0)
    if "index" in normalized or "canonical" in normalized:
        return (1.0, 1.0)
    return (0.0, 1.0)


def fixture_semantic_embedding(text: str) -> Vector:
    normalized = text.casefold()
    if "technical seo" in normalized or "crawling" in normalized:
        return (1.0, 0.0, 0.0)
    if "index" in normalized or "canonical" in normalized:
        return (0.6, 0.8, 0.0)
    return (0.0, 1.0, 0.0)


def fixture_bge_reranker_score(keyword: str, text: str) -> float:
    normalized_keyword = keyword.casefold()
    normalized_text = text.casefold()

    if normalized_keyword in normalized_text:
        return 0.98
    if "index" in normalized_text or "canonical" in normalized_text:
        return 0.74

    keyword_tokens = {
        token for token in re.findall(r"[a-z0-9]+", normalized_keyword) if token
    }
    if not keyword_tokens:
        return 0.12

    text_tokens = set(re.findall(r"[a-z0-9]+", normalized_text))
    shared_tokens = keyword_tokens & text_tokens
    if not shared_tokens:
        return 0.12

    overlap_ratio = len(shared_tokens) / len(keyword_tokens)
    return round(min(0.12 + (0.78 * overlap_ratio), 0.97), 6)


def cosine_similarity(left: Vector, right: Vector) -> float:
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    dot = sum(left_value * right_value for left_value, right_value in zip(left, right))
    return dot / (left_norm * right_norm)
