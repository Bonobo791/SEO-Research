from __future__ import annotations

import sys
from pathlib import Path

import polars as pl

from seo_rank.stats import ranking_explainability_viz as viz
from seo_rank.stats.ranking_explainability_viz import (
    _open_with_system_viewer,
    write_curated_model_visualization,
    write_entity_relevance_visualization,
)
from seo_rank.stats.textrazor_explainability import summarize_ranking_explainability


def _explainability_panel_frame() -> pl.DataFrame:
    rows: list[dict[str, object]] = []
    for keyword_index in range(1, 11):
        target_keyword_id = f"kw-{keyword_index}"
        keyword_offset = keyword_index * 0.01
        for serp_rank in range(1, 5):
            signal = float(4 - serp_rank) + keyword_offset
            rows.append(
                {
                    "run_id": "run-1",
                    "target_keyword_id": target_keyword_id,
                    "target_keyword": f"keyword {keyword_index}",
                    "canonical_url_hash": f"url-{keyword_index}-{serp_rank}",
                    "serp_rank": serp_rank,
                    "page_text_length": 120 + (keyword_index * 3) + serp_rank,
                    "referring_domains_count": 120 + (keyword_index * 3) + serp_rank,
                    "deprecated_html_tags": (keyword_index + serp_rank) % 3 == 0,
                    "bge_normalized_score": signal,
                    "gemini_doc_retrieval_normalized_score": signal - 0.1,
                    "gemini_semantic_similarity_normalized_score": signal - 0.2,
                    "textrazor_entity_confidence_score": signal + 0.5,
                    "textrazor_entity_relevance_score": signal + 0.4,
                    "textrazor_entailment_score": signal + 0.05,
                    "textrazor_relation_count": int(serp_rank + 1),
                    "textrazor_property_count": int(serp_rank),
                }
            )
    return pl.DataFrame(rows)


def test_interactive_backend_candidates_exclude_macosx_off_darwin(monkeypatch) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    assert "MacOSX" not in viz._interactive_backend_candidates()


def test_import_pyplot_uses_agg_when_no_interactive_backend_works(monkeypatch) -> None:
    monkeypatch.setattr(
        viz,
        "_backend_can_create_figure",
        lambda _plt: False,
    )
    plt, can_show = viz._import_pyplot(interactive=True)
    import matplotlib

    assert can_show is False
    assert "agg" in matplotlib.get_backend().lower()
    plt.close("all")


def test_write_curated_model_visualization_creates_png(tmp_path: Path) -> None:
    panel = _explainability_panel_frame()
    summary = summarize_ranking_explainability(
        panel,
        panel,
        run_id="run-1",
        rank_depth="top_20",
    )
    output_path = tmp_path / "ranking_r2_curated_model.png"

    result = write_curated_model_visualization(
        panel,
        summary["multivariate_curated"],
        output_path=output_path,
        run_id="run-1",
        rank_depth="top_20",
    )

    assert result is not None
    assert result.output_path == output_path
    assert output_path.exists()
    assert output_path.stat().st_size > 0
    assert result.display_message is None


def test_write_curated_model_visualization_show_invokes_pyplot_show(
    monkeypatch,
    tmp_path: Path,
) -> None:
    panel = _explainability_panel_frame()
    summary = summarize_ranking_explainability(
        panel,
        panel,
        run_id="run-1",
        rank_depth="top_20",
    )
    shown: list[bool] = []

    def _fake_show(*_args, **_kwargs) -> None:
        shown.append(True)

    import matplotlib.pyplot as plt

    monkeypatch.setattr(
        "seo_rank.stats.ranking_explainability_viz._import_pyplot",
        lambda *, interactive: (plt, True),
    )
    monkeypatch.setattr(plt, "show", _fake_show)

    result = write_curated_model_visualization(
        panel,
        summary["multivariate_curated"],
        output_path=tmp_path / "ranking_r2_curated_model.png",
        run_id="run-1",
        rank_depth="top_20",
        show=True,
    )

    assert result is not None
    assert shown == [True]
    assert result.display_message == "Opened curated model chart in a matplotlib window."


def test_write_entity_relevance_visualization_creates_png(tmp_path: Path) -> None:
    panel = _explainability_panel_frame()
    summary = summarize_ranking_explainability(
        panel,
        panel,
        run_id="run-1",
        rank_depth="top_20",
    )
    entity_relevance = next(
        entry
        for entry in summary["textrazor"]["univariate"]
        if entry["label"] == "entity_relevance"
    )
    output_path = tmp_path / "ranking_r2_entity_relevance.png"

    result = write_entity_relevance_visualization(
        panel,
        entity_relevance,
        output_path=output_path,
        run_id="run-1",
        rank_depth="top_20",
    )

    assert result is not None
    assert result.output_path == output_path
    assert output_path.exists()
    assert output_path.stat().st_size > 0


def test_write_curated_model_visualization_retries_with_agg_when_gui_backend_breaks(
    monkeypatch,
    tmp_path: Path,
) -> None:
    panel = _explainability_panel_frame()
    summary = summarize_ranking_explainability(
        panel,
        panel,
        run_id="run-1",
        rank_depth="top_20",
    )
    opened: list[Path] = []
    build_attempts = {"count": 0}
    real_build = viz._build_curated_model_figure

    def _flaky_build(*args, **kwargs):
        build_attempts["count"] += 1
        if build_attempts["count"] == 1:
            raise ImportError("cannot import name '_macosx'")
        return real_build(*args, **kwargs)

    import matplotlib.pyplot as plt

    monkeypatch.setattr(
        viz,
        "_import_pyplot",
        lambda *, interactive: (plt, True) if interactive else (plt, False),
    )
    monkeypatch.setattr(viz, "_build_curated_model_figure", _flaky_build)
    monkeypatch.setattr(
        viz,
        "_open_with_system_viewer",
        lambda path: opened.append(path) or True,
    )

    output_path = tmp_path / "ranking_r2_curated_model.png"
    result = write_curated_model_visualization(
        panel,
        summary["multivariate_curated"],
        output_path=output_path,
        run_id="run-1",
        rank_depth="top_20",
        show=True,
    )

    assert result is not None
    assert build_attempts["count"] == 2
    assert opened == [output_path]
    assert output_path.exists()


def test_write_curated_model_visualization_falls_back_to_system_viewer(
    monkeypatch,
    tmp_path: Path,
) -> None:
    panel = _explainability_panel_frame()
    summary = summarize_ranking_explainability(
        panel,
        panel,
        run_id="run-1",
        rank_depth="top_20",
    )
    opened: list[Path] = []

    import matplotlib.pyplot as plt

    monkeypatch.setattr(
        "seo_rank.stats.ranking_explainability_viz._import_pyplot",
        lambda *, interactive: (plt, False),
    )
    monkeypatch.setattr(
        "seo_rank.stats.ranking_explainability_viz._open_with_system_viewer",
        lambda path: opened.append(path) or True,
    )

    output_path = tmp_path / "ranking_r2_curated_model.png"
    result = write_curated_model_visualization(
        panel,
        summary["multivariate_curated"],
        output_path=output_path,
        run_id="run-1",
        rank_depth="top_20",
        show=True,
    )

    assert result is not None
    assert opened == [output_path]
    assert "default image viewer" in (result.display_message or "")


def test_write_curated_model_visualization_skips_when_model_not_computed(
    tmp_path: Path,
) -> None:
    panel = pl.DataFrame()
    result = write_curated_model_visualization(
        panel,
        {"status": "skipped", "skipped_reason": "no_usable_rows"},
        output_path=tmp_path / "ranking_r2_curated_model.png",
        run_id="run-1",
        rank_depth="top_20",
    )

    assert result is None


def test_open_with_system_viewer_returns_false_when_launcher_missing(
    monkeypatch,
    tmp_path: Path,
) -> None:
    image_path = tmp_path / "chart.png"
    image_path.write_text("not-a-real-png", encoding="utf-8")

    def _raise_not_found(*_args, **_kwargs):
        raise FileNotFoundError("xdg-open")

    monkeypatch.setattr("subprocess.run", _raise_not_found)

    assert _open_with_system_viewer(image_path) is False
