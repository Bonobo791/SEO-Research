from __future__ import annotations

from pathlib import Path

from scripts.append_fixups import (
    append_fixup_section,
    infer_fixup_prefix,
    is_code_fixup,
    next_fixup_ids,
    parse_fixup_rows,
)


def test_infer_fixup_prefix_from_goals_phase() -> None:
    goals = "# Goals\n\nBuild Phase 4.77 adapter validation.\n"
    assert infer_fixup_prefix(goals) == "S477"


def test_infer_fixup_prefix_from_phase_five_goals() -> None:
    goals = "# Goals\n\nBuild Phase 5 statistical analysis.\n"
    assert infer_fixup_prefix(goals) == "S5"


def test_parse_fixup_rows_reads_auto_table_lines() -> None:
    text = """
Some review prose.

## FIXUPS_ROWS

| AUTO | Add schema test for drift | 4.77 Slice 1 | required | open |
| AUTO | Rename helper in normalize.py | 4.77 Slice 2 | nice-to-have | open |
"""
    rows = parse_fixup_rows(text)
    assert len(rows) == 2
    assert rows[0]["fix"] == "Add schema test for drift"
    assert rows[0]["priority"] == "required"


def test_is_code_fixup_rejects_documentation_items() -> None:
    assert is_code_fixup(
        {
            "fix": "Document breaking CLI flag in README.md",
            "phase": "4.77 Slice 1",
            "priority": "nice-to-have",
        }
    ) is False
    assert is_code_fixup(
        {
            "fix": "Add failing test for missing required field",
            "phase": "4.77 Slice 1",
            "priority": "required",
        }
    ) is True
    assert is_code_fixup(
        {
            "fix": "Publish policy matrix in ARCHITECTURE.md",
            "phase": "4.77 docs",
            "priority": "required",
        }
    ) is False


def test_next_fixup_ids_increments_from_existing_file(tmp_path: Path) -> None:
    fixups = tmp_path / "FIXUPS.md"
    fixups.write_text(
        "| S477-02 | old | 4.77 | nice-to-have | open |\n| S476-99 | old | 4.76 | nice-to-have | open |\n",
        encoding="utf-8",
    )
    assert next_fixup_ids(fixups, "S477", 2) == ["S477-03", "S477-04"]


def test_append_fixup_section_inserts_before_how_to_use(tmp_path: Path) -> None:
    fixups = tmp_path / "FIXUPS.md"
    fixups.write_text(
        "# Small fixes backlog\n\n## How to use this file\n\n- Pick items\n",
        encoding="utf-8",
    )
    rows = [
        {
            "fix": "Add adapter boundary test",
            "phase": "4.77 Slice 1",
            "priority": "required",
            "status": "open",
        }
    ]
    added = append_fixup_section(
        fixups,
        section_title="Code review — automated slice loop",
        rows=rows,
        prefix="S477",
    )
    text = fixups.read_text(encoding="utf-8")
    assert added == ["S477-01"]
    assert "| S477-01 | Add adapter boundary test |" in text
    assert "## Code review — automated slice loop" in text
    assert text.index("## Code review") < text.index("## How to use this file")
