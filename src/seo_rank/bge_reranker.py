"""Live BGE reranker helpers for page-level similarity scoring."""
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
from types import MethodType
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
    reranker = build_reranker(
        BGE_RERANKER_MODEL,
        use_fp16=True,
        devices=["cuda"],
    )
    _patch_prepare_for_model_compatibility(reranker)
    return reranker


def _patch_prepare_for_model_compatibility(reranker: object) -> None:
    tokenizer = getattr(reranker, "tokenizer", None)
    if tokenizer is None or hasattr(tokenizer, "prepare_for_model"):
        return

    def prepare_for_model(
        self,
        ids,
        pair_ids=None,
        truncation=None,
        max_length=None,
        padding=False,
        **kwargs,
    ):
        del padding, kwargs

        first_sequence = list(ids)
        second_sequence = list(pair_ids) if pair_ids is not None else None
        bos_token_id = getattr(self, "bos_token_id", None)
        eos_token_id = getattr(self, "eos_token_id", None)
        if bos_token_id is None:
            bos_token_id = getattr(self, "cls_token_id", None)
        if eos_token_id is None:
            eos_token_id = getattr(self, "sep_token_id", None)
        if bos_token_id is None or eos_token_id is None:
            raise BgeRerankerError(
                "Live BGE scoring requires tokenizer special tokens that "
                "are unavailable in this transformers version"
            )

        if second_sequence is None:
            limit = (
                None
                if max_length is None
                else max(0, max_length - self.num_special_tokens_to_add(pair=False))
            )
            if limit is not None and len(first_sequence) > limit:
                first_sequence = first_sequence[:limit]
            input_ids = [bos_token_id, *first_sequence, eos_token_id]
        else:
            limit = (
                None
                if max_length is None
                else max(0, max_length - self.num_special_tokens_to_add(pair=True))
            )
            if limit is not None:
                overflow = len(first_sequence) + len(second_sequence) - limit
                if overflow > 0:
                    if truncation in (None, True, "only_second", "longest_first"):
                        second_trim = min(overflow, len(second_sequence))
                        second_sequence = second_sequence[: len(second_sequence) - second_trim]
                        overflow -= second_trim
                        if overflow > 0:
                            first_sequence = first_sequence[: len(first_sequence) - overflow]
                    else:
                        second_sequence = second_sequence[:limit]
            input_ids = [
                bos_token_id,
                *first_sequence,
                eos_token_id,
                eos_token_id,
                *second_sequence,
                eos_token_id,
            ]

        return {"input_ids": input_ids}

    try:
        tokenizer.prepare_for_model = MethodType(prepare_for_model, tokenizer)
    except Exception as error:  # pragma: no cover - defensive compatibility fallback
        raise BgeRerankerError(
            "Live BGE scoring requires a mutable tokenizer for transformers "
            "compatibility"
        ) from error


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
