import polars as pl

from seo_rank.stats.model_inputs import drop_incomplete_control_rows


def test_drop_incomplete_control_rows_keeps_rows_complete_on_all_controls() -> None:
    frame = pl.DataFrame(
        {
            "site_scale": [1.0, None, 2.0, 3.0],
            "authority_proxy": [0.5, 0.1, None, 0.2],
            "other": [1, 2, 3, 4],
        }
    )

    result = drop_incomplete_control_rows(frame)

    assert result.to_dicts() == [
        {"site_scale": 1.0, "authority_proxy": 0.5, "other": 1},
        {"site_scale": 3.0, "authority_proxy": 0.2, "other": 4},
    ]


def test_drop_incomplete_control_rows_returns_frame_when_no_controls_present() -> None:
    frame = pl.DataFrame({"other": [1, 2]})

    assert drop_incomplete_control_rows(frame).equals(frame)
