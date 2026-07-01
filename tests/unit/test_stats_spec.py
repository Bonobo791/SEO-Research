from pathlib import Path

import seo_rank.stats as stats
from seo_rank.stats import artifacts
from seo_rank.stats.spec import load_analysis_spec


def test_stats_package_exports_module_surface() -> None:
    assert stats.spec.__name__ == "seo_rank.stats.spec"
    assert stats.panel.__name__ == "seo_rank.stats.panel"
    assert stats.spearman.__name__ == "seo_rank.stats.spearman"
    assert stats.regression.__name__ == "seo_rank.stats.regression"
    assert stats.diagnostics.__name__ == "seo_rank.stats.diagnostics"
    assert stats.bh.__name__ == "seo_rank.stats.bh"
    assert stats.artifacts.__name__ == "seo_rank.stats.artifacts"


def test_load_analysis_spec_reads_repo_root_yaml() -> None:
    analysis_spec = load_analysis_spec()

    assert analysis_spec.path == Path("analysis_spec.v1.yaml")
    assert analysis_spec.version == "v1"
    assert analysis_spec.estimand_version == "v1"
    assert analysis_spec.primary_backend == "bge"
    assert analysis_spec.backend_order == (
        "bge",
        "gemini_doc_retrieval",
        "gemini_semantic_similarity",
    )
    assert analysis_spec.estimand["outcome"] == "-log(serp_rank)"


def test_build_stats_output_metadata_exposes_estimand_version() -> None:
    analysis_spec = load_analysis_spec()
    metadata = artifacts.build_stats_output_metadata(analysis_spec)

    assert metadata == {
        "analysis_spec_version": "v1",
        "estimand_version": "v1",
        "primary_backend": "bge",
        "backend_order": [
            "bge",
            "gemini_doc_retrieval",
            "gemini_semantic_similarity",
        ],
    }
