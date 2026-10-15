---
description: Create or update DESIGN.md from requirements and visual references.
argument-hint: <requirements, image, or reference URL>
---
Create or update `DESIGN.md` in the current workspace from the user's request and available project context.
Write only `DESIGN.md`; do not implement the design or create or edit HTML, CSS, JavaScript, assets, or other project files.

Request: $ARGUMENTS

Use supplied images and URLs, plus installed skills or MCP tools, only when they materially improve the specification. Do one focused pass; avoid broad research and implementation.

Document the user flow, information hierarchy, layout, components, responsive behavior, design tokens, accessibility, loading/empty/error/disabled states, and acceptance checks that apply. Match existing product patterns unless the user requests a change. State assumptions and unresolved decisions. Do not create any file besides `DESIGN.md`.