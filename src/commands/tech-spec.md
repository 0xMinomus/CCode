---
description: Write TECH-SPEC.md for an approved feature or system change.
argument-hint: <feature or technical request>
---
Create or update `TECH-SPEC.md` in the current workspace for the requested change.
Write only `TECH-SPEC.md`; do not edit implementation files or execute the plan.

Request: $ARGUMENTS

Inspect workspace instructions, the relevant implementation, callers, tests, and existing `PRD.md` or `DESIGN.md` when present. Use relevant available skills or MCP tools only when useful; do not assume unavailable tools.

Specify scope and non-goals, current behavior, proposed data flow and component boundaries, APIs or schemas, errors and security boundaries, migration and rollback needs, and verification criteria. Prefer existing patterns and the smallest complete design. Separate observed facts from assumptions. Do not edit implementation files.