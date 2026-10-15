---
description: Record an architecture decision in docs/adr/.
argument-hint: <decision and context>
---
This slash command is an explicit request to execute the task below, not a skill name to look up. Begin the requested work; do not ask whether to proceed. Follow applicable workspace instructions and safety boundaries.

You may use any relevant user-enabled skills and connected MCP tools available in this session. Use them as helpers, not as a replacement for this task or permission to expand its scope. If a helper is unavailable, continue with available tools when possible; do not install or repeatedly search for helpers.

Inspect only relevant context in one focused pass. Do not repeat searches, tool calls, or planning without new evidence. Proceed with labeled assumptions for nonblocking gaps; ask only if missing information prevents safe completion. Once the requested outcome is verified, stop and report the result briefly. Never claim an unperformed action.

Task: Create one new numbered ADR in docs/adr/ for the requested decision. Inspect existing ADRs, choose the next unused number and a short slug, and include status, context, decision, consequences, and alternatives. Never overwrite an ADR or invent approval; use proposed status if the decision is not yet accepted. Do not edit implementation.

User input: $ARGUMENTS
