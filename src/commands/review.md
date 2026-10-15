---
description: Review the current changes for concrete regressions and risks.
argument-hint: [scope or files]
---
This slash command is an explicit request to execute the task below, not a skill name to look up. Begin the requested work; do not ask whether to proceed. Follow applicable workspace instructions and safety boundaries.

You may use any relevant user-enabled skills and connected MCP tools available in this session. Use them as helpers, not as a replacement for this task or permission to expand its scope. If a helper is unavailable, continue with available tools when possible; do not install or repeatedly search for helpers.

Inspect only relevant context in one focused pass. Do not repeat searches, tool calls, or planning without new evidence. Proceed with labeled assumptions for nonblocking gaps; ask only if missing information prevents safe completion. Once the requested outcome is verified, stop and report the result briefly. Never claim an unperformed action.

Task: Review the requested changes without editing files. Inspect the diff, affected callers, and relevant tests. Report actionable findings ordered by severity with exact file/line evidence and affected behavior. Prioritize correctness, security, data loss, and compatibility; omit style preferences. If no findings are supported, say so and identify verification limits.

User input: $ARGUMENTS
