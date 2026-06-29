"""Live BGE reranker helpers for page-level similarity scoring."""

import math
from collections.abc import Sequence

BGE_RERANKER_MODEL = "BAAI/bge-reranker-v2-m3"


class BgeRerankerError(RuntimeError):
    """Raised when live BGE reranking cannot be produced."""


def load_bge_reranker(
    *,
    build_reranker=None,
    is_gpu_available=None,
):
    if is_gpu_available is None:
        is_gpu_available = default_is_gpu_available
    if not is_gpu_available():
        raise BgeRerankerError("Live BGE scoring requires a CUDA GPU")
    if build_reranker is None:
        build_reranker = default_build_reranker
    return build_reranker(
        BGE_RERANKER_MODEL,
        use_fp16=True,
        devices=["cuda"],
    )


def compute_bge_page_similarity_scores(
    keyword: str,
    pages: Sequence[dict[str, str]],
    *,
    reranker=None,
    load_reranker=None,
) -> list[dict[str, object]]:
    if load_reranker is None:
        load_reranker = load_bge_reranker

    valid_pages = [
        page
        for page in pages
        if isinstance(page.get("url"), str) and isinstance(page.get("text"), str)
    ]
    if not valid_pages:
        return []

    if reranker is None:
        reranker = load_reranker()
    pairs = [[keyword, str(page["text"])] for page in valid_pages]
    raw_scores = reranker.compute_score(pairs)
    if isinstance(raw_scores, (int, float)):
        raw_scores = [float(raw_scores)]

    scores: list[dict[str, object]] = []
    for page, raw_score in zip(valid_pages, raw_scores):
        raw_value = round(float(raw_score), 6)
        scores.append(
            {
                "url": str(page["url"]),
                "page_similarity": {
                    "bge": {
                        "raw_score": raw_value,
                        "normalized_score": round(sigmoid(float(raw_score)), 6),
                    }
                },
            }
        )
    return scores


def default_is_gpu_available() -> bool:
    try:
        import torch
    except ImportError as error:
        raise BgeRerankerError(
            "Live BGE scoring requires the optional dependency "
            "'FlagEmbedding'. Install with: pip install -e '.[similarity,dev]'"
        ) from error
    return bool(torch.cuda.is_available())


def default_build_reranker(model_name: str, **kwargs):
    try:
        from FlagEmbedding import FlagReranker
    except ImportError as error:
        raise BgeRerankerError(
            "Live BGE scoring requires the optional dependency "
            "'FlagEmbedding'. Install with: pip install -e '.[similarity,dev]'"
        ) from error
    return FlagReranker(model_name, **kwargs)


def sigmoid(value: float) -> float:
    return 1.0 / (1.0 + math.exp(-value))
