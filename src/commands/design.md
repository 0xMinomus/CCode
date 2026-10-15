---
description: Create or update DESIGN.md from requirements and visual references.
argument-hint: <requirements, image, or reference URL>
---
Create or update `DESIGN.md` in the current workspace from the user's request and available project context.

Request: $ARGUMENTS

Read relevant workspace instructions, existing product documents, and nearby UI code. Use attached images and reference URLs when available tools can inspect them. Use relevant installed skills or MCP tools only when they help; never assume an unavailable tool or claim an unread reference was inspected.

Document the user flow, information hierarchy, layout, components, responsive behavior, design tokens, accessibility, loading/empty/error/disabled states, and acceptance checks that apply. Match existing product patterns unless the user requests a change. State assumptions and unresolved decisions. Do not edit implementation files.