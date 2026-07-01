#!/usr/bin/env bash
# Automated slice loop:
#   1. Codex ($sdlc) — implement the next slice only
#   2. Cursor Agent (/code-reviewer) — code review on the diff
#   3. Cursor Agent (/senior-qa) — release test-gap review on the diff
# Appends code-only follow-ups to FIXUPS.md from steps 2–3.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

REVIEW_DIR="${REVIEW_DIR:-$REPO_ROOT/.reviews}"
mkdir -p "$REVIEW_DIR"

CODEX_PROMPT="${CODEX_PROMPT:-\$sdlc Work on the next slice. Implementation only — do not run code review or senior QA; Cursor Agent handles those after this step.}"
CODE_REVIEW_PROMPT="${CODE_REVIEW_PROMPT:-/code-reviewer Review the current uncommitted diff. Include only code and test fixups — skip documentation-only suggestions (README, ARCHITECTURE, GOALS, ROADMAP, TESTING, FIXUPS, SDLC docs). Do not edit any files. End your response with a section exactly titled:

## FIXUPS_ROWS

Markdown table rows only (no header row, no separator). Each row:
| AUTO | <fix description> | <phase from GOALS.md> | <required or nice-to-have> | open |}"

SENIOR_QA_PROMPT="${SENIOR_QA_PROMPT:-/senior-qa Review the diff for release test gaps. Do not create or edit any documentation files. Do not run scaffold_test_plan.py or add new docs. Include only code and test fixups — skip documentation-only suggestions. Do not edit any files. End your response with a section exactly titled:

## FIXUPS_ROWS

Markdown table rows only (no header row, no separator). Each row:
| AUTO | <fix description> | <phase from GOALS.md> | <required or nice-to-have> | open |}"

CODEX_BIN="${CODEX_BIN:-codex}"
AGENT_BIN="${AGENT_BIN:-agent}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

CODEX_SANDBOX="${CODEX_SANDBOX:-workspace-write}"
CODEX_EXTRA_ARGS="${CODEX_EXTRA_ARGS:-}"

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "error: required command not found: $1" >&2
    exit 1
  fi
}

require_cmd "$CODEX_BIN"
require_cmd "$AGENT_BIN"
require_cmd "$PYTHON_BIN"

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"

if [[ "${SKIP_CODEX:-0}" != "1" ]]; then
  echo "==> Step 1/3: Codex (\$sdlc) — next slice implementation"
  echo "    Prompt: ${CODEX_PROMPT}"
  # shellcheck disable=SC2086
  "$CODEX_BIN" exec "$CODEX_PROMPT" \
    -C "$REPO_ROOT" \
    -s "$CODEX_SANDBOX" \
    -o "$REVIEW_DIR/codex-slice-last.txt" \
    $CODEX_EXTRA_ARGS \
    2>&1 | tee "$REVIEW_DIR/codex-slice-${timestamp}.log"
else
  echo "==> Step 1/3: Codex skipped (SKIP_CODEX=1)"
fi

echo "==> Step 2/3: Cursor Agent — /code-reviewer"
"$AGENT_BIN" --print --trust --workspace "$REPO_ROOT" "$CODE_REVIEW_PROMPT" \
  2>&1 | tee "$REVIEW_DIR/code-review-${timestamp}.log"

"$PYTHON_BIN" "$REPO_ROOT/scripts/append_fixups.py" \
  --source "$REVIEW_DIR/code-review-${timestamp}.log" \
  --section "Code review — automated slice loop" \
  --fixups "$REPO_ROOT/FIXUPS.md" \
  --goals "$REPO_ROOT/GOALS.md"

echo "==> Step 3/3: Cursor Agent — /senior-qa"
"$AGENT_BIN" --print --trust --workspace "$REPO_ROOT" "$SENIOR_QA_PROMPT" \
  2>&1 | tee "$REVIEW_DIR/senior-qa-${timestamp}.log"

"$PYTHON_BIN" "$REPO_ROOT/scripts/append_fixups.py" \
  --source "$REVIEW_DIR/senior-qa-${timestamp}.log" \
  --section "Senior QA — automated slice loop" \
  --fixups "$REPO_ROOT/FIXUPS.md" \
  --goals "$REPO_ROOT/GOALS.md"

echo "Done. Logs: $REVIEW_DIR"
echo "Updated: $REPO_ROOT/FIXUPS.md"
