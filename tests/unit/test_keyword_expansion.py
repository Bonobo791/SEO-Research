from pathlib import Path

from seo_rank.cli import RunConfig, build_offline_payload


def test_offline_payload_uses_single_keyword_default(tmp_path: Path) -> None:
    payload = build_offline_payload(
        RunConfig(
            seed="technical seo",
            location="United States",
            language="en",
            device="desktop",
            depth=3,
            output_dir=tmp_path,
            model_name="fixture-similarity-v1",
            dry_run=True,
            skip_textrazor=True,
        )
    )

    keywords = payload["keywords"]
    assert isinstance(keywords, list)
    assert len(keywords) == 1
    assert keywords[0] == "technical seo"
    assert "technical seo audit" not in keywords
    assert "technical seo topic 23" not in keywords

    raw_provider_data = payload["raw_provider_data"]
    assert isinstance(raw_provider_data, dict)
    dataforseo = raw_provider_data["dataforseo"]
    assert isinstance(dataforseo, dict)
    assert dataforseo["keyword_expansion"]["provider"] == "dataforseo"
