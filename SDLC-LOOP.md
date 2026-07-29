<!--
SEO Research — SEO Factors Research Tool
Copyright (C) 2026 Andrew Philip Weilbacher

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published
by the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program. If not, see <https://www.gnu.org/licenses/>.

Commercial licensing: contact@marketingprowess.simplelogin.com — see COMMERCIAL.md
-->
# SDLC Loop


Codex does not have a native `/sdlc` command. This file is the honest replacement.

## The Loop

1. Frame the slice
   Restate the task, set a scope guard, state confidence (`HIGH` / `MEDIUM` / `LOW`), and say what will prove the work is done.
2. Red first
   Write the failing test first when the task is code-shaped.
   If the task is setup, auth, or environment repair, define the failing observable first instead of pretending it is unit-testable.
3. Green with the smallest change
   Make the narrowest change that can satisfy the red check.
4. Prove it
   Run the targeted checks, capture the evidence, and make sure the result matches the original success condition.
5. Review the diff
   Read the diff back, note risks, and remove junk before thinking about a commit.
6. Commit only after proof
   Commits happen after tests and proof, not before.
7. Escalate honestly
   If blocked, name the blocker, show the evidence, and propose the next move.

## Task routing gate

Identify the execution lane before giving instructions: CLI, Desktop/computer-use, browser automation, or human-only setup.

Use `Desktop/computer-use` first when a task crosses Microsoft browser sign-in, developer program qualification, account pickers, MFA, tenant consent, Office UI, admin portal state, or other auth-heavy screens that the CLI cannot safely prove.

After naming the lane, provide the handoff prompt and guardrails before any CLI or browser steps. Keep credentials, MFA, tenant consent, subscription creation, license/admin changes, sends, deletes, and policy publishing behind explicit human action.

## Testing Shape

- Most checks should be unit tests.
- Some should be integration tests around real boundaries.
- A small number should be E2E checks.
- Use browser E2E where it helps, but do not pretend browser tests replace desktop-only flows such as Word COM.

## Setup And Auth Work

For setup, installs, PATH repair, and auth-heavy workflows:

- Prefer full access.
- Capture before/after evidence.
- Re-run the bootstrap or health check after each fix.
- Treat the health check as the prove-it gate.

## Codex Desktop handoff

Use Codex Desktop handoff when setup crosses a browser, desktop app, admin portal, screenshot, or auth window that CLI cannot see. Codex Desktop is available on macOS and Windows.

From the repo root:

```bash
codex app .
```

Computer-use work must report back as evidence, not just chat. Prefer a repo-local `.reviews/desktop-computer-use-report.md` or equivalent artifact with findings, blockers, screenshots by path, and the next CLI action.

Human-in-the-loop boundary:

- Codex may navigate, read screens, click non-destructive controls, and explain state.
- The user handles credentials, MFA, tenant consent, sends, deletes, license/admin changes, and policy publishing.
- Return to CLI for code changes, tests, commits, and push.

## Microsoft 365 auth lane

For Microsoft 365 setup, prefer Graph PowerShell first when `Get-MgContext` works. Browser or Desktop sign-in success is not enough by itself; verify the resulting script context before treating the lane as proven.

Fallback proof rules:

- Require tenant id plus expected work account before accepting a raw OAuth REST or device-code proof.
- Treat personal Microsoft account success as invalid for work-tenant validation.
- Keep fallback proofs read-only unless the user approves a draft, send, delete, license/admin, or policy action for that exact run.
- Record the proven lane, current status, artifacts, and next CLI action in `.reviews/` so the next agent does not repeat auth discovery from chat memory.
