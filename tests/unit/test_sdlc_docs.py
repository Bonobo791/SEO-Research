import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_goals_and_roadmap_define_active_scope_and_backlog() -> None:
    goals = (ROOT / "GOALS.md").read_text(encoding="utf-8")
    roadmap = (ROOT / "ROADMAP.md").read_text(encoding="utf-8")

    assert "active-scope contract" in goals
    assert "Build the first offline-verifiable Python CLI scaffold" in goals
    assert "Current Backlog" in roadmap
    assert "When `GOALS.md` exists, it is the active" in roadmap


def test_manifest_records_resolved_pytest_commands() -> None:
    manifest = json.loads((ROOT / ".codex-sdlc/manifest.json").read_text(encoding="utf-8"))
    resolved = manifest.get("resolved_values", {})
    scan = manifest.get("scan", {})

    test_command = resolved.get("test_command") or scan.get("test_command")
    single_test_command = resolved.get("single_test_file_command") or scan.get(
        "single_test_file_command"
    )

    assert test_command == "python -m pytest"
    assert single_test_command == "python -m pytest tests/unit/test_cli_run.py"
    assert (resolved.get("test_framework") or scan.get("test_framework")) == "pytest"


def test_product_docs_exist_and_reference_core_contracts() -> None:
    architecture = ROOT / "docs/architecture/ARCHITECTURE.md"
    implementation = ROOT / "docs/implementation/dataforseo-textrazor-ranking-similarity-plan.md"
    adr_0001 = ROOT / "docs/architecture/adr/0001-keyword-cluster-observational-analysis.md"
    adr_0002 = ROOT / "docs/architecture/adr/0002-censored-top20-validation-and-reporting.md"

    for path in (architecture, implementation, adr_0001, adr_0002):
        assert path.is_file(), f"missing product doc: {path.relative_to(ROOT)}"

    architecture_text = architecture.read_text(encoding="utf-8")
    implementation_text = implementation.read_text(encoding="utf-8")
    adr_0001_text = adr_0001.read_text(encoding="utf-8")
    adr_0002_text = adr_0002.read_text(encoding="utf-8")

    assert "DataForSEO" in architecture_text
    assert "TextRazor" in architecture_text
    assert "offline" in implementation_text
    assert "observational" in adr_0001_text
    assert "top-20" in adr_0002_text or "top 20" in adr_0002_text
