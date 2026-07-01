from __future__ import annotations

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
from seo_rank.gemini_embeddings import (
    GEMINI_EMBEDDING_DIMENSIONALITY,
    GEMINI_EMBEDDING_MODEL,
    cosine_similarity,
    prepare_semantic_input,
    to_vector,
)


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


def compute_semantic_similarity_scores(
    keyword: str,
    blocks: Sequence[dict[str, str]],
    *,
    api_key: str,
    embed_content: Callable[..., Sequence[float]],
) -> list[dict[str, object]]:
    keyword_vector = to_vector(
        embed_content(
            prepare_semantic_input(keyword),
            api_key=api_key,
            model=GEMINI_EMBEDDING_MODEL,
            output_dimensionality=GEMINI_EMBEDDING_DIMENSIONALITY,
        )
    )

    scores: list[dict[str, object]] = []
    for block in blocks:
        label = block["label"]
        text = block["text"]
        block_vector = to_vector(
            embed_content(
                prepare_semantic_input(text),
                api_key=api_key,
                model=GEMINI_EMBEDDING_MODEL,
                output_dimensionality=GEMINI_EMBEDDING_DIMENSIONALITY,
            )
        )
        scores.append(
            {
                "label": label,
                "score": round(cosine_similarity(keyword_vector, block_vector), 6),
            }
        )
    return scores


def build_live_embed_content(api_key: str) -> Callable[..., Sequence[float]]:
    from google import genai
    from google.genai.types import EmbedContentConfig

    client = genai.Client(vertexai=False, api_key=api_key)

    def embed_content(
        content: str,
        *,
        api_key: str,
        model: str,
        output_dimensionality: int,
    ) -> Sequence[float]:
        if api_key != client.models._api_client.api_key:
            raise ValueError("embed_content called with an unexpected api key")
        response = client.models.embed_content(
            model=model,
            contents=content,
            config=EmbedContentConfig(output_dimensionality=output_dimensionality),
        )
        embeddings = getattr(response, "embeddings", None)
        if not embeddings:
            raise RuntimeError("Gemini embedding response did not include vectors")
        values = getattr(embeddings[0], "values", None)
        if values is None:
            raise RuntimeError("Gemini embedding response contained invalid values")
        return values

    return embed_content


def main() -> int:
    ensure_project_env_loaded()
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("GEMINI_API_KEY is required in the project .env")

    try:
        scores = compute_semantic_similarity_scores(
            KEYWORD,
            TEXT_BLOCKS,
            api_key=api_key,
            embed_content=build_live_embed_content(api_key),
        )
    except Exception as error:
        raise SystemExit(f"Gemini embedding request failed: {error}") from error

    print(f"Keyword: {KEYWORD}")
    for index, row in enumerate(
        sorted(scores, key=lambda item: item["score"], reverse=True), start=1
    ):
        print(f"{index}. {row['label']} - {row['score']:.6f}")

    print()
    print(json.dumps({"keyword": KEYWORD, "scores": scores}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
