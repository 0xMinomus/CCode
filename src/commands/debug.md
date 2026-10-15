---
description: Reproduce a reported bug, find its root cause, and verify the fix.
argument-hint: <observed failure and reproduction steps>
---
This slash command is an explicit request to execute the task below, not a skill name to look up. Begin the requested work; do not ask whether to proceed. Follow applicable workspace instructions and safety boundaries.

You may use any relevant user-enabled skills and connected MCP tools available in this session. Use them as helpers, not as a replacement for this task or permission to expand its scope. If a helper is unavailable, continue with available tools when possible; do not install or repeatedly search for helpers.

Inspect only relevant context in one focused pass. Do not repeat searches, tool calls, or planning without new evidence. Proceed with labeled assumptions for nonblocking gaps; ask only if missing information prevents safe completion. Once the requested outcome is verified, stop and report the result briefly. Never claim an unperformed action.

Task: Diagnose and fix the reported failure. Reproduce when practical, trace the shared failing path and callers, and fix the root cause without suppressing errors or weakening security. Add a focused behavioral regression check where appropriate and verify the original scenario. State any reproduction limit honestly. Do not stop at a diagnosis or deploy without authorization.

User input: $ARGUMENTS
