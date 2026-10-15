---
description: Run the relevant checks for a requested behavior or change.
argument-hint: [feature, files, or test scope]
---
This slash command is an explicit request to execute the task below, not a skill name to look up. Begin the requested work; do not ask whether to proceed. Follow applicable workspace instructions and safety boundaries.

You may use any relevant user-enabled skills and connected MCP tools available in this session. Use them as helpers, not as a replacement for this task or permission to expand its scope. If a helper is unavailable, continue with available tools when possible; do not install or repeatedly search for helpers.

Inspect only relevant context in one focused pass. Do not repeat searches, tool calls, or planning without new evidence. Proceed with labeled assumptions for nonblocking gaps; ask only if missing information prevents safe completion. Once the requested outcome is verified, stop and report the result briefly. Never claim an unperformed action.

Task: Run the smallest relevant tests/checks, plus broader checks required by workspace instructions. Use isolated data for stateful checks. Do not edit files, send provider prompts, access live services, or execute destructive actions without appropriate explicit authorization. Report actual commands, pass/fail results, and coverage limits; do not claim unrun checks.

User input: $ARGUMENTS
