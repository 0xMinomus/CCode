---
description: Write TEST-PLAN.md with acceptance and regression checks.
argument-hint: <feature or acceptance criteria>
---
Create or update `TEST-PLAN.md` in the current workspace for the requested behavior.

Request: $ARGUMENTS

Read workspace instructions and relevant requirements, design, implementation, and existing tests. Define observable checks for normal behavior, boundaries, state transitions, failures, persistence, and compatibility where applicable. Name the relevant test layers and commands only when repository evidence supports them. Separate automated checks from manual checks. Avoid tests that only repeat source text, wiring, or mock echoes. Do not modify code or run tests unless the user also asks for execution.