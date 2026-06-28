from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_goals_and_roadmap_define_active_scope_and_backlog() -> None:
    goals = (ROOT / "GOALS.md").read_text(encoding="utf-8")
    roadmap = (ROOT / "ROADMAP.md").read_text(encoding="utf-8")

    assert "active-scope contract" in goals
    assert "Build the first offline-verifiable Python CLI scaffold" in goals
    assert "Current Backlog" in roadmap
    assert "When `GOALS.md` exists, it is the active" in roadmap
