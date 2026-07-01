"""Stats artifact helpers."""

from __future__ import annotations

from collections.abc import Mapping

from seo_rank.stats.spec import AnalysisSpec


def build_stats_output_metadata(spec: AnalysisSpec) -> Mapping[str, object]:
    return {
        "analysis_spec_version": spec.version,
        "estimand_version": spec.estimand_version,
        "primary_backend": spec.primary_backend,
        "backend_order": list(spec.backend_order),
    }
