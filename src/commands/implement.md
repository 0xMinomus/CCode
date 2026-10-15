---
description: Implement an approved request or existing plan in the workspace.
argument-hint: <approved change>
---
This slash command is an explicit request to execute the task below, not a skill name to look up. Begin the requested work; do not ask whether to proceed. Follow applicable workspace instructions and safety boundaries.

You may use any relevant user-enabled skills and connected MCP tools available in this session. Use them as helpers, not as a replacement for this task or permission to expand its scope. If a helper is unavailable, continue with available tools when possible; do not install or repeatedly search for helpers.

Inspect only relevant context in one focused pass. Do not repeat searches, tool calls, or planning without new evidence. Proceed with labeled assumptions for nonblocking gaps; ask only if missing information prevents safe completion. Once the requested outcome is verified, stop and report the result briefly. Never claim an unperformed action.

Task: Implement the requested change now. Inspect relevant code, callers, tests, and approved specifications. Make the smallest complete change using existing architecture and UI patterns. Update relevant tests and required documentation, run applicable checks, and exercise the changed path. Do not add unrelated features or commit, push, or deploy without authorization.

User input: $ARGUMENTS
