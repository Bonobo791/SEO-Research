import os
from pathlib import Path

from seo_rank.env import find_env_file, load_project_env, parse_env_file


def test_parse_env_file_reads_key_value_pairs_and_skips_comments(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "# comment",
                "SEO_RANK_RUN_LIVE_INTEGRATION=0",
                'DATAFORSEO_LOGIN="quoted-login"',
                "TEXTRAZOR_API_KEY=plain-key",
            ]
        ),
        encoding="utf-8",
    )

    assert parse_env_file(env_path) == {
        "SEO_RANK_RUN_LIVE_INTEGRATION": "0",
        "DATAFORSEO_LOGIN": "quoted-login",
        "TEXTRAZOR_API_KEY": "plain-key",
    }


def test_load_project_env_overrides_shell_values_from_repo_env_file(
    monkeypatch,
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "pyproject.toml").write_text("[project]\nname='seo-rank'\n", encoding="utf-8")
    (project_root / ".env").write_text(
        "SEO_RANK_RUN_LIVE_INTEGRATION=0\nSEO_RANK_ENABLE_LIVE_PROVIDERS=0\n",
        encoding="utf-8",
    )

    monkeypatch.chdir(project_root)
    monkeypatch.setenv("SEO_RANK_RUN_LIVE_INTEGRATION", "1")

    loaded = load_project_env(start=project_root)

    assert loaded == project_root / ".env"
    assert os.environ["SEO_RANK_RUN_LIVE_INTEGRATION"] == "0"
    assert os.environ["SEO_RANK_ENABLE_LIVE_PROVIDERS"] == "0"


def test_ensure_project_env_loaded_runs_only_once(monkeypatch, tmp_path: Path) -> None:
    import seo_rank.env as env_module

    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "pyproject.toml").write_text("[project]\nname='seo-rank'\n", encoding="utf-8")
    (project_root / ".env").write_text("SEO_RANK_RUN_LIVE_INTEGRATION=0\n", encoding="utf-8")

    monkeypatch.chdir(project_root)
    monkeypatch.setattr(env_module, "_ENV_LOADED", False)
    monkeypatch.setenv("SEO_RANK_RUN_LIVE_INTEGRATION", "1")

    first = env_module.ensure_project_env_loaded(start=project_root)
    assert first == project_root / ".env"
    assert os.environ["SEO_RANK_RUN_LIVE_INTEGRATION"] == "0"

    monkeypatch.setenv("SEO_RANK_RUN_LIVE_INTEGRATION", "1")
    second = env_module.ensure_project_env_loaded(start=project_root)
    assert second == project_root / ".env"
    assert os.environ["SEO_RANK_RUN_LIVE_INTEGRATION"] == "1"


def test_find_env_file_walks_up_to_pyproject_root(tmp_path: Path) -> None:
    project_root = tmp_path / "repo"
    nested = project_root / "src" / "nested"
    nested.mkdir(parents=True)
    (project_root / "pyproject.toml").write_text("[project]\nname='seo-rank'\n", encoding="utf-8")
    env_file = project_root / ".env"
    env_file.write_text("SEO_RANK_RUN_LIVE_INTEGRATION=0\n", encoding="utf-8")

    assert find_env_file(start=nested) == env_file
