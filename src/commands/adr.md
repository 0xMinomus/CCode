---
description: Record an accepted architecture decision in docs/adr/.
argument-hint: <decision and context>
---
Write one Architecture Decision Record under `docs/adr/` for the decision in the request.
Create or update only that ADR file; do not modify other project files.

Request: $ARGUMENTS

Read workspace instructions and relevant architecture docs. Identify the next unused zero-padded number from existing ADR filenames. Use a short kebab-case slug. If the decision is not made, present the concrete options and tradeoffs instead of recording an accepted decision. Do not overwrite an existing ADR.

Include status, context, decision, consequences, and considered alternatives. Cite repository evidence for current behavior. Keep assumptions explicit. Do not edit implementation files.