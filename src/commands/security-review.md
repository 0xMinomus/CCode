---
description: Audit the requested code path for evidence-backed security issues.
argument-hint: [feature, files, or trust boundary]
---
This slash command is an explicit request to execute the task below, not a skill name to look up. Begin the requested work; do not ask whether to proceed. Follow applicable workspace instructions and safety boundaries.

You may use any relevant user-enabled skills and connected MCP tools available in this session. Use them as helpers, not as a replacement for this task or permission to expand its scope. If a helper is unavailable, continue with available tools when possible; do not install or repeatedly search for helpers.

Inspect only relevant context in one focused pass. Do not repeat searches, tool calls, or planning without new evidence. Proceed with labeled assumptions for nonblocking gaps; ask only if missing information prevents safe completion. Once the requested outcome is verified, stop and report the result briefly. Never claim an unperformed action.

Task: Audit the requested scope without editing files. Trace reachable trust boundaries, authorization, validation, filesystem/network access, secret handling, and failure paths. Report evidence-backed findings with severity, attacker capability, impact, reachable path, and remediation. Separate confirmed vulnerabilities from unverified risks. Do not expose secrets or probe live systems without authorization.

User input: $ARGUMENTS
