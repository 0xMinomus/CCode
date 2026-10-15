---
description: Implement an approved request or existing plan in the workspace.
argument-hint: <approved change>
---
Implement the approved change described by the request.

Request: $ARGUMENTS

Read all applicable workspace instructions first. Inspect the relevant code, callers, and tests before editing. Follow the existing architecture and UI family. Use available skills or MCP tools only when relevant and available. Make the smallest complete change; do not add unrequested retries, abstractions, dependencies, or features.

Update affected tests and documentation required by the workspace. Run the relevant checks and exercise the changed path. Report changed files, actual verification, and any blocker. Do not commit, push, deploy, or change unrelated user data unless explicitly requested.