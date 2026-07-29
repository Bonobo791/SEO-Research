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
# Task Completion


No lint, typecheck, format, or build step exists in this project (confirmed AGENTS.md — do not search for them). Verification = tests.

Definition of done for a coding task:
1. Relevant tests written first and passing (TDD). If touching a module, run its unit test file.
2. Full unit suite green: `python -m pytest` (collects `tests/unit` only).
3. NEVER commit with failing tests. Live integration tests (`-m integration`) are opt-in and not required for normal completion.
4. Commit gate (no CI): `node .codex/hooks/git-guard.cjs prove --reviewed` must pass before commit.
5. After code changes, refresh knowledge graph: `graphify update .` (AST-only, no API cost).

Commit only when the user asks.
