from __future__ import annotations

import logging
import json
import os
import sys
from pathlib import Path
from typing import Callable, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
REPO_SRC = REPO_ROOT / "src"
DEPS_DIR = Path("/tmp/gemini_deps")

if str(DEPS_DIR) not in sys.path:
    sys.path.insert(0, str(DEPS_DIR))
if str(REPO_SRC) not in sys.path:
    sys.path.insert(0, str(REPO_SRC))

from seo_rank.env import ensure_project_env_loaded
from seo_rank.bge_reranker import load_bge_reranker, sigmoid
from seo_rank.gemini_embeddings import (
    GEMINI_EMBEDDING_DIMENSIONALITY,
    GEMINI_EMBEDDING_MODEL,
    build_live_embed_content,
    cosine_similarity,
    prepare_document,
    prepare_query,
    prepare_semantic_input,
    to_vector,
)
from seo_rank.similarity import fixture_bge_reranker_score
from seo_rank.textrazor import (
    TextRazorCredentials,
    build_entity_request,
    execute_textrazor_request,
    normalize_page_metrics,
    validate_textrazor_credentials,
)


logger = logging.getLogger(__name__)

KEYWORD = "best northwest houston realtors"

TEXT_BLOCKS: list[dict[str, str]] = [
    {
        "label": "Michele Harmon Team",
        "text": (
            "Michele Harmon Team | Northwest Houston Real Estate\n"
            "Why Choose Us?\n"
            "You get 7 Agents for the price of 1!\n"
            "All 5 of our Sales Partners work for 100% commission and they are "
            "committed to selling your home!\n"
            "Buyers have phone access to a live agent 7 days a week.\n"
            "We have an established social media presence.\n"
            "Customer satisfaction is our number ONE priority.\n"
            "We bring a wealth of experience and deep knowledge of the local real estate market.\n"
            "Personalized Service, Comprehensive Marketing, Network, Negotiation Skills, "
            "Tech-Savvy, Community Engagement, Transparency, Track Record, Market Insights, "
            "Post-Sale Support.\n"
            "Top Areas & Neighborhoods: Tomball, Copperfield, Cypress, Katy, Magnolia, "
            "Montgomery, Pinehurst, Spring, The Woodlands, Conroe."
        ),
    },
    {
        "label": "Ryan & Royale Jockers",
        "text": (
            "Ryan & Royale Jockers Team\n"
            "You deserve the best! Don't settle for less, work with the best!\n"
            "Why buy or sell with THE JOCKERS TEAM?\n"
            "The Jockers team has SOLD and LISTED more homes than any other team in the "
            "Champions office.\n"
            "Our fabulous reviews speak for themselves.\n"
            "Our fabulous team members strive to always provide five-star service to our clients.\n"
            "We wanted to offer something to make moving easier. Buy or sell with us and "
            "use either of these trucks for free."
        ),
    },
    {
        "label": "The Lippincott Team",
        "text": (
            "The Lippincott Team\n"
            "#1 Team in Northwest Houston\n"
            "Award Winning Northwest Houston Realtors\n"
            "We’ve won the Houston Business Journal’s Residential Real Estate Awards 9 times.\n"
            "Work with a Team With a Proven Track Record.\n"
            "We are your friendly greater Northwest Houston realtor experts.\n"
            "Serving Northwest Houston.\n"
            "We’re Award-winning Northwest Houston Realtors.\n"
            "We provide up-to-date real estate information, expert marketing services, and local resources."
        ),
    },
]


class _FixtureBgeReranker:
    def compute_score(self, pairs: Sequence[Sequence[str]]) -> list[float]:
        return [
            fixture_bge_reranker_score(keyword_value, text_value)
            for keyword_value, text_value in pairs
        ]


def _load_bge_reranker_or_fixture():
    try:
        return load_bge_reranker()
    except Exception as error:  # pragma: no cover - exercised via regression tests
        logger.warning(
            "live BGE unavailable, using fixture scores instead: %s",
            error,
        )
        return _FixtureBgeReranker()


def _textrazor_entity_scores(
    label: str,
    text: str,
    *,
    textrazor_api_key: str,
    textrazor_transport=None,
) -> dict[str, dict[str, float]]:
    logger.info("requesting textrazor metrics label=%s text_chars=%d", label, len(text))
    response = execute_textrazor_request(
        build_entity_request({"text": text}),
        credentials=TextRazorCredentials(api_key=textrazor_api_key),
        transport=textrazor_transport,
    )
    metrics = normalize_page_metrics(response, url=f"analysis://{label}")
    confidence = float(metrics["textrazor_entity_confidence_score"])
    relevance = float(metrics["textrazor_entity_relevance_score"])
    logger.info(
        "received textrazor metrics label=%s confidence=%s relevance=%s",
        label,
        confidence,
        relevance,
    )
    return {
        "textrazor_entity_confidence_score": {
            "raw_score": round(confidence, 6),
            "normalized_score": round(confidence, 6),
        },
        "textrazor_entity_relevance_score": {
            "raw_score": round(relevance, 6),
            "normalized_score": round(relevance, 6),
        },
    }


def compute_semantic_similarity_scores(
    keyword: str,
    blocks: Sequence[dict[str, str]],
    *,
    api_key: str,
    textrazor_api_key: str,
    embed_content: Callable[..., Sequence[float]],
    reranker=None,
    textrazor_transport=None,
) -> list[dict[str, object]]:
    keyword_document_vector = to_vector(
        embed_content(
            prepare_query(keyword),
            api_key=api_key,
            model=GEMINI_EMBEDDING_MODEL,
            output_dimensionality=GEMINI_EMBEDDING_DIMENSIONALITY,
        )
    )
    keyword_semantic_vector = to_vector(
        embed_content(
            prepare_semantic_input(keyword),
            api_key=api_key,
            model=GEMINI_EMBEDDING_MODEL,
            output_dimensionality=GEMINI_EMBEDDING_DIMENSIONALITY,
        )
    )

    valid_blocks = [
        block
        for block in blocks
        if isinstance(block.get("label"), str) and isinstance(block.get("text"), str)
    ]
    if not valid_blocks:
        logger.info("computing semantic similarity keyword=%s blocks=0 valid_blocks=0", keyword)
        return []
    logger.info(
        "computing semantic similarity keyword=%s blocks=%d valid_blocks=%d",
        keyword,
        len(blocks),
        len(valid_blocks),
    )
    pairs = [[keyword, block["text"]] for block in valid_blocks]
    if reranker is None:
        reranker = _load_bge_reranker_or_fixture()
    try:
        raw_bge_scores = reranker.compute_score(pairs)
    except Exception as error:
        if isinstance(reranker, _FixtureBgeReranker):
            raise
        logger.warning("live BGE scoring failed, using fixture scores instead: %s", error)
        raw_bge_scores = _FixtureBgeReranker().compute_score(pairs)
    if isinstance(raw_bge_scores, (int, float)):
        raw_bge_scores = [float(raw_bge_scores)]

    scores: list[dict[str, object]] = []
    for block, raw_bge_score in zip(valid_blocks, raw_bge_scores):
        label = block["label"]
        text = block["text"]
        document_vector = to_vector(
            embed_content(
                prepare_document(text, title=label),
                api_key=api_key,
                model=GEMINI_EMBEDDING_MODEL,
                output_dimensionality=GEMINI_EMBEDDING_DIMENSIONALITY,
            )
        )
        semantic_vector = to_vector(
            embed_content(
                prepare_semantic_input(text),
                api_key=api_key,
                model=GEMINI_EMBEDDING_MODEL,
                output_dimensionality=GEMINI_EMBEDDING_DIMENSIONALITY,
            )
        )
        document_similarity = round(
            cosine_similarity(keyword_document_vector, document_vector),
            6,
        )
        semantic_similarity = round(
            cosine_similarity(keyword_semantic_vector, semantic_vector),
            6,
        )
        scores.append(
            {
                "label": label,
                "page_similarity": {
                    "bge": {
                        "raw_score": round(float(raw_bge_score), 6),
                        "normalized_score": round(sigmoid(float(raw_bge_score)), 6),
                    },
                    "gemini_doc_retrieval": {
                        "raw_score": document_similarity,
                        "normalized_score": document_similarity,
                    },
                    "gemini_semantic_similarity": {
                        "raw_score": semantic_similarity,
                        "normalized_score": semantic_similarity,
                    },
                    **_textrazor_entity_scores(
                        label,
                        text,
                        textrazor_api_key=textrazor_api_key,
                        textrazor_transport=textrazor_transport,
                    ),
                },
            }
        )
        logger.info(
            "scored block label=%s bge=%s doc=%s semantic=%s textrazor_confidence=%s textrazor_relevance=%s",
            label,
            scores[-1]["page_similarity"]["bge"]["raw_score"],
            document_similarity,
            semantic_similarity,
            scores[-1]["page_similarity"]["textrazor_entity_confidence_score"]["raw_score"],
            scores[-1]["page_similarity"]["textrazor_entity_relevance_score"]["raw_score"],
        )
    return scores

def main() -> int:
    ensure_project_env_loaded()
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("GEMINI_API_KEY is required in the project .env")
    textrazor_credentials = validate_textrazor_credentials(os.environ)

    logger.info("starting analysis keyword=%s blocks=%d", KEYWORD, len(TEXT_BLOCKS))
    try:
        scores = compute_semantic_similarity_scores(
            KEYWORD,
            TEXT_BLOCKS,
            api_key=api_key,
            textrazor_api_key=textrazor_credentials.api_key,
            embed_content=build_live_embed_content(api_key),
        )
    except Exception as error:
        raise SystemExit(f"Gemini embedding request failed: {error}") from error
    logger.info("completed analysis keyword=%s scored_blocks=%d", KEYWORD, len(scores))

    print(f"Keyword: {KEYWORD}")
    for index, row in enumerate(
        sorted(
            scores,
            key=lambda item: item["page_similarity"]["gemini_semantic_similarity"][
                "raw_score"
            ],
            reverse=True,
        ),
        start=1,
    ):
        page_similarity = row["page_similarity"]
        bge = page_similarity["bge"]
        document_relevance = page_similarity["gemini_doc_retrieval"]
        semantic = page_similarity["gemini_semantic_similarity"]
        textrazor_confidence = page_similarity["textrazor_entity_confidence_score"]
        textrazor_relevance = page_similarity["textrazor_entity_relevance_score"]
        print(
            f"{index}. {row['label']} - "
            f"BGE: {bge['raw_score']:.6f} (normalized {bge['normalized_score']:.6f}) | "
            f"Gemini document relevance: {document_relevance['raw_score']:.6f} | "
            f"Gemini semantic similarity: {semantic['raw_score']:.6f} | "
            f"TextRazor entity confidence: {textrazor_confidence['raw_score']:.6f} | "
            f"TextRazor entity relevance: {textrazor_relevance['raw_score']:.6f}"
        )

    print()
    print(json.dumps({"keyword": KEYWORD, "scores": scores}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
