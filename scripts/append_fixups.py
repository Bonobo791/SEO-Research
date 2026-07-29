#!/usr/bin/env python3
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

"""Parse agent review output and append code-only rows to FIXUPS.md."""

from __future__ import annotations

import argparse
import re
from datetime import date
from pathlib import Path
from typing import Iterable

FIXUPS_MARKER = "## FIXUPS_ROWS"
HOW_TO_USE_HEADING = "## How to use this file"
TABLE_HEADER = "| ID | Fix | Phase | Priority | Status |"
TABLE_SEPARATOR = "| --- | --- | --- | --- | --- |"
ID_PATTERN = re.compile(r"\b(S\d+)-(\d+)\b", re.IGNORECASE)
PHASE_PATTERN = re.compile(r"Phase\s+(\d+)(?:\.(\d+))?", re.IGNORECASE)

DOC_PATH_MARKERS = (
    "README.md",
    "ARCHITECTURE.md",
    "GOALS.md",
    "ROADMAP.md",
    "TESTING.md",
    "FIXUPS.md",
    "SDLC.md",
    "SDLC-LOOP.md",
    "PROVE-IT.md",
    "START-SDLC.md",
    "docs/",
    "docs/qa",
    "changelog",
    "release note",
    "scaffold_test_plan",
    "test plan doc",
)

DOC_VERB_PREFIXES = (
    "document ",
    "document:",
    "add a one-line pointer",
    "publish ",
    "fix ",
    "update ",
    "keep ",
    "scaffold ",
    "add phase",
    "add manual sign-off checklist",
    "state unit baseline",
)


def infer_fixup_prefix(goals_text: str, *, default: str = "S5") -> str:
    match = PHASE_PATTERN.search(goals_text)
    if not match:
        return default
    major, minor = match.groups()
    return f"S{major}{minor or ''}"


def _split_table_row(line: str) -> list[str]:
    stripped = line.strip()
    if not stripped.startswith("|"):
        return []
    cells = [cell.strip() for cell in stripped.strip("|").split("|")]
    return cells


def _is_separator_row(cells: list[str]) -> bool:
    return bool(cells) and all(set(cell) <= {"-", " "} and cell for cell in cells)


def parse_fixup_rows(text: str) -> list[dict[str, str]]:
    section = text
    marker_index = text.find(FIXUPS_MARKER)
    if marker_index >= 0:
        section = text[marker_index + len(FIXUPS_MARKER) :]

    rows: list[dict[str, str]] = []
    for line in section.splitlines():
        cells = _split_table_row(line)
        if len(cells) < 5 or _is_separator_row(cells):
            continue
        fix_id, fix, phase, priority, status = cells[:5]
        if fix_id.upper() in {"ID", "AUTO"} and fix.lower() == "fix":
            continue
        rows.append(
            {
                "fix": fix,
                "phase": phase,
                "priority": priority,
                "status": status or "open",
            }
        )
    return rows


def _mentions_doc_path(fix: str) -> bool:
    lowered = fix.lower()
    return any(marker.lower() in lowered for marker in DOC_PATH_MARKERS)


def is_code_fixup(row: dict[str, str]) -> bool:
    phase = row.get("phase", "")
    fix = row.get("fix", "")
    if "doc" in phase.lower():
        return False
    if _mentions_doc_path(fix):
        return False
    lowered = fix.lower()
    if any(lowered.startswith(prefix) for prefix in DOC_VERB_PREFIXES):
        if _mentions_doc_path(fix):
            return False
    return True


def existing_fixup_ids(fixups_path: Path) -> set[str]:
    text = fixups_path.read_text(encoding="utf-8")
    return {match.group(0).upper() for match in ID_PATTERN.finditer(text)}


def next_fixup_ids(fixups_path: Path, prefix: str, count: int) -> list[str]:
    prefix = prefix.upper()
    max_number = 0
    for fix_id in existing_fixup_ids(fixups_path):
        match = ID_PATTERN.fullmatch(fix_id)
        if not match or match.group(1).upper() != prefix:
            continue
        max_number = max(max_number, int(match.group(2)))
    return [f"{prefix}-{index:02d}" for index in range(max_number + 1, max_number + 1 + count)]


def _normalize_existing_fix_text(fixups_path: Path) -> set[str]:
    text = fixups_path.read_text(encoding="utf-8")
    fixes: set[str] = set()
    for line in text.splitlines():
        cells = _split_table_row(line)
        if len(cells) >= 2 and not _is_separator_row(cells):
            fixes.add(cells[1].strip().lower())
    return fixes


def append_fixup_section(
    fixups_path: Path,
    *,
    section_title: str,
    rows: Iterable[dict[str, str]],
    prefix: str,
) -> list[str]:
    code_rows = [row for row in rows if is_code_fixup(row)]
    if not code_rows:
        return []

    existing_fixes = _normalize_existing_fix_text(fixups_path)
    deduped: list[dict[str, str]] = []
    for row in code_rows:
        key = row["fix"].strip().lower()
        if key in existing_fixes:
            continue
        existing_fixes.add(key)
        deduped.append(row)
    if not deduped:
        return []

    assigned_ids = next_fixup_ids(fixups_path, prefix, len(deduped))
    today = date.today().isoformat()
    block_lines = [
        f"## {section_title} ({today})",
        "",
        f"Appended by `scripts/next-slice-loop.sh`. Code / tests only.",
        "",
        TABLE_HEADER,
        TABLE_SEPARATOR,
    ]
    for fix_id, row in zip(assigned_ids, deduped, strict=True):
        block_lines.append(
            f"| {fix_id} | {row['fix']} | {row['phase']} | {row['priority']} | {row['status']} |"
        )
    block_lines.append("")
    block = "\n".join(block_lines)

    original = fixups_path.read_text(encoding="utf-8")
    if HOW_TO_USE_HEADING in original:
        updated = original.replace(HOW_TO_USE_HEADING, f"{block}{HOW_TO_USE_HEADING}", 1)
    else:
        updated = original.rstrip() + "\n\n" + block
    fixups_path.write_text(updated, encoding="utf-8")
    return assigned_ids


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path, help="Agent output file")
    parser.add_argument("--fixups", required=True, type=Path, help="FIXUPS.md path")
    parser.add_argument("--goals", type=Path, help="GOALS.md path for ID prefix inference")
    parser.add_argument("--section", required=True, help="Section title to append")
    parser.add_argument("--prefix", help="Fixup ID prefix (default: infer from GOALS.md)")
    args = parser.parse_args()

    goals_path = args.goals or args.fixups.parent / "GOALS.md"
    prefix = args.prefix
    if not prefix:
        goals_text = goals_path.read_text(encoding="utf-8") if goals_path.is_file() else ""
        prefix = infer_fixup_prefix(goals_text)

    review_text = args.source.read_text(encoding="utf-8")
    rows = parse_fixup_rows(review_text)
    added = append_fixup_section(
        args.fixups,
        section_title=args.section,
        rows=rows,
        prefix=prefix,
    )
    if added:
        print(f"Added {len(added)} fixup row(s) to {args.fixups}: {', '.join(added)}")
    else:
        print(f"No new code fixups to append from {args.source}")


if __name__ == "__main__":
    main()
